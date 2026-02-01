# Copyright AGNTCY Contributors (https://github.com/agntcy)
# SPDX-License-Identifier: Apache-2.0

"""
Travel Supervisor Graph

LangGraph implementation for the travel agent workflow.
This graph orchestrates the travel planning process:
1. Supervisor classifies user intent
2. Travel search extracts parameters and finds optimal plans
3. General responses handle non-travel queries

Node Flow:
    supervisor_node → travel_search_node or general_node → END
                   ↑                    ↓
                   └── reflection_node ←┘
"""

import logging
import uuid
from datetime import datetime

from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph import MessagesState, StateGraph, END
from ioa_observe.sdk.decorators import agent, graph

from agents.travel.serpapi_tools import search_flights, search_hotels
from agents.travel.travel_logic import find_cheapest_plan
from agents.supervisors.travel.graph.models import TravelSearchArgs
from common.llm import get_llm
from config.config import TRAVEL_HOTEL_CHECKIN_GAP_HOURS

logger = logging.getLogger("lungo.travel.supervisor.graph")


class NodeStates:
    """
    Node state identifiers for the travel graph workflow.
    
    SUPERVISOR: Entry point - classifies user intent
    TRAVEL_SEARCH: Handles travel planning requests
    GENERAL_INFO: Handles non-travel queries
    REFLECTION: Determines if further action is needed
    """
    SUPERVISOR = "travel_supervisor"
    TRAVEL_SEARCH = "travel_search"
    GENERAL_INFO = "general"
    REFLECTION = "reflection"


class GraphState(MessagesState):
    """
    State object passed between graph nodes.
    
    Extends MessagesState with:
    - next_node: Routing decision for conditional edges
    - full_response: Accumulated response for streaming
    - search_params: Extracted travel search parameters
    """
    next_node: str
    full_response: str = ""
    search_params: dict = {}


@agent(name="travel_agent")
class TravelGraph:
    """
    LangGraph-based travel agent that finds optimal flight + hotel combinations.
    
    This agent:
    1. Parses user travel requests using LLM structured output
    2. Searches for flights and hotels via SerpAPI
    3. Applies timing constraints (hotel check-in after flight arrival)
    4. Returns the cheapest valid combination
    
    Example usage:
        graph = TravelGraph()
        result = await graph.serve("Find me the cheapest trip from LAX to Tokyo, Jan 15-22")
    """
    
    def __init__(self):
        """Initialize the travel graph and compile the workflow."""
        self.graph = self.build_graph()

    @graph(name="travel_graph")
    def build_graph(self) -> CompiledStateGraph:
        """
        Construct and compile the LangGraph workflow.
        
        Agent Flow:
        
        supervisor_node
            - Classifies user intent: "travel_search" vs "general"
            - Routes to appropriate handler node
        
        travel_search_node
            - Extracts trip parameters (origin, destination, dates) from user message
            - If missing params → asks user for clarification
            - Searches flights and hotels via SerpAPI
            - Finds cheapest valid plan with timing constraints
            - Formats and returns results
        
        general_node
            - Handles non-travel queries
            - Provides helpful guidance about travel agent capabilities
        
        reflection_node
            - Evaluates if user request has been satisfied
            - Decides whether to continue or end conversation
        
        Returns:
            CompiledStateGraph: Ready-to-execute LangGraph instance
        """
        # LLM instances - lazy initialized on first use
        self.supervisor_llm = None
        self.reflection_llm = None
        self.travel_search_llm = None

        workflow = StateGraph(GraphState)

        # --- 1. Define Node States ---
        workflow.add_node(NodeStates.SUPERVISOR, self._supervisor_node)
        workflow.add_node(NodeStates.TRAVEL_SEARCH, self._travel_search_node)
        workflow.add_node(NodeStates.GENERAL_INFO, self._general_response_node)
        workflow.add_node(NodeStates.REFLECTION, self._reflection_node)

        # --- 2. Define the Agentic Workflow ---
        workflow.set_entry_point(NodeStates.SUPERVISOR)

        # Supervisor routes to appropriate handler based on intent
        workflow.add_conditional_edges(
            NodeStates.SUPERVISOR,
            lambda state: state["next_node"],
            {
                NodeStates.TRAVEL_SEARCH: NodeStates.TRAVEL_SEARCH,
                NodeStates.GENERAL_INFO: NodeStates.GENERAL_INFO,
            },
        )

        # Travel search goes to reflection for follow-up handling
        workflow.add_edge(NodeStates.TRAVEL_SEARCH, NodeStates.REFLECTION)
        
        # General info ends the conversation
        workflow.add_edge(NodeStates.GENERAL_INFO, END)

        # Reflection decides whether to continue or end
        workflow.add_conditional_edges(
            NodeStates.REFLECTION,
            lambda state: state["next_node"],
            {
                NodeStates.SUPERVISOR: NodeStates.SUPERVISOR,
                END: END,
            },
        )

        return workflow.compile()

    async def _supervisor_node(self, state: GraphState) -> dict:
        """
        Classify user intent and route to appropriate handler.
        
        Determines if the user is:
        - Asking about travel (flights, hotels, trips) → travel_search
        - Asking something else → general
        
        Args:
            state: Current graph state with user messages
        
        Returns:
            Updated state with next_node routing decision
        """
        if not self.supervisor_llm:
            self.supervisor_llm = get_llm()

        user_message = state["messages"]

        # Prompt to classify user intent
        prompt = PromptTemplate(
            template="""You are a travel planning assistant. Analyze the user's message to determine their intent.

Based on the user's message, respond with ONE of these options:
- 'travel_search' - if the user is asking about:
    * Finding flights or airfare
    * Booking hotels or accommodation
    * Planning a trip with origin, destination, or dates
    * Comparing travel prices
    * Any travel-related query
- 'general' - if the message is:
    * A greeting or general question
    * Unrelated to travel planning
    * Asking about your capabilities

User message: {user_message}

Respond with ONLY 'travel_search' or 'general':""",
            input_variables=["user_message"]
        )

        chain = prompt | self.supervisor_llm
        response = chain.invoke({"user_message": user_message})
        intent = response.content.strip().lower()

        logger.info(f"Supervisor classified intent as: {intent}")

        if "travel_search" in intent:
            return {"next_node": NodeStates.TRAVEL_SEARCH, "messages": user_message}
        else:
            return {"next_node": NodeStates.GENERAL_INFO, "messages": user_message}

    async def _travel_search_node(self, state: GraphState) -> dict:
        """
        Handle travel search requests by extracting params and finding optimal plans.
        
        This node:
        1. Extracts trip parameters from user message using structured LLM output
        2. If params are missing, asks user for clarification
        3. Searches for flights and hotels via SerpAPI
        4. Finds cheapest combination meeting timing constraints
        5. Returns formatted travel plan
        
        Args:
            state: Current graph state with user messages
        
        Returns:
            Updated state with AI response containing travel plan or clarification request
        """
        if not self.travel_search_llm:
            self.travel_search_llm = get_llm(streaming=False)

        # Get latest user message
        user_msg = next((m for m in reversed(state["messages"]) if m.type == "human"), None)
        if not user_msg:
            return {"messages": [AIMessage(content="I didn't receive your travel request. Please tell me your origin, destination, and travel dates.")]}

        logger.info(f"Processing travel search: {user_msg.content}")

        # Step 1: Extract travel parameters using structured output
        try:
            params = await self._extract_travel_params(user_msg.content)
        except Exception as e:
            logger.error(f"Failed to extract travel params: {e}")
            return {"messages": [AIMessage(content="I had trouble understanding your request. Could you please specify your origin, destination, and travel dates?")]}

        # Step 2: Check for missing parameters
        if not params.has_all_params:
            missing = params.missing_params or "some details"
            clarification_msg = f"I'd be happy to help plan your trip! To find the best flight and hotel deals, I need a few more details:\n\n"
            
            if not params.origin:
                clarification_msg += "- **Origin**: Where will you be departing from? (city or airport code)\n"
            if not params.destination:
                clarification_msg += "- **Destination**: Where do you want to go?\n"
            if not params.start_date:
                clarification_msg += "- **Start Date**: When do you want to leave? (YYYY-MM-DD)\n"
            if not params.end_date:
                clarification_msg += "- **End Date**: When do you want to return?\n"
            
            return {"messages": [AIMessage(content=clarification_msg)], "search_params": params.model_dump()}

        # Step 3: Search for flights and hotels
        logger.info(f"Searching: {params.origin} -> {params.destination}, {params.start_date} to {params.end_date}")
        
        try:
            # Search for flights
            flights = await search_flights(
                params.origin,
                params.destination,
                params.start_date,
                params.end_date,
            )
            
            if not flights:
                return {"messages": [AIMessage(content=f"I couldn't find any flights from {params.origin} to {params.destination} for those dates. Please try different dates or locations.")]}

            # Search for hotels
            hotels = await search_hotels(
                params.destination,
                params.start_date,
                params.end_date,
            )
            
            if not hotels:
                return {"messages": [AIMessage(content=f"I found flights but couldn't find hotels in {params.destination}. You might want to search for hotels in a nearby area.")]}

            # Step 4: Find cheapest valid plan
            plan = find_cheapest_plan(flights, hotels)
            
            if not plan:
                # No valid combination found - explain why
                return {"messages": [AIMessage(content=
                    f"I found {len(flights)} flights and {len(hotels)} hotels, but couldn't find a combination that works.\n\n"
                    f"This usually happens when hotel check-in times are too early for your flight arrival. "
                    f"The system requires at least {TRAVEL_HOTEL_CHECKIN_GAP_HOURS} hours between flight arrival and hotel check-in.\n\n"
                    f"Try searching for an earlier departure date or a later check-in time."
                )]}

            # Step 5: Format and return the result
            response = self._format_travel_plan(plan, params)
            return {"messages": [AIMessage(content=response)], "full_response": response}

        except Exception as e:
            logger.error(f"Error during travel search: {e}")
            return {"messages": [AIMessage(content=f"I encountered an error while searching for your trip: {str(e)}\n\nPlease try again or modify your search criteria.")]}

    async def _extract_travel_params(self, user_message: str) -> TravelSearchArgs:
        """
        Extract travel parameters from user message using LLM structured output.
        
        Uses the TravelSearchArgs model to ensure proper extraction of:
        - Origin city/airport
        - Destination city/airport
        - Start date
        - End date
        
        Args:
            user_message: Raw user input string
        
        Returns:
            TravelSearchArgs with extracted parameters
        """
        extraction_llm = get_llm(streaming=False).with_structured_output(TravelSearchArgs, strict=True)
        
        # Get current year for date parsing context
        current_year = datetime.now().year
        
        prompt = f"""Extract travel search parameters from the user's message.

Current year for reference: {current_year}

User message: {user_message}

Rules:
- For dates, convert to YYYY-MM-DD format (e.g., "Jan 15" → "{current_year}-01-15")
- If year is not specified, assume {current_year} or {current_year + 1} (whichever makes sense)
- Airport codes should be uppercase (e.g., "LAX", "JFK", "NRT")
- City names are acceptable for both origin and destination
- Set has_all_params to true ONLY if origin, destination, start_date, AND end_date are all present
- List missing parameters in missing_params field"""

        result = await extraction_llm.ainvoke(prompt)
        logger.info(f"Extracted params: {result}")
        return result

    def _format_travel_plan(self, plan: dict, params: TravelSearchArgs) -> str:
        """
        Format a travel plan into a user-friendly response.
        
        Creates a well-structured summary with:
        - Total cost prominently displayed
        - Flight details (airline, times, stops)
        - Hotel details (name, price, rating)
        - Trip summary with timing info
        
        Args:
            plan: Travel plan from find_cheapest_plan()
            params: Original search parameters
        
        Returns:
            Formatted string response
        """
        flight = plan["flight"]
        hotel = plan["hotel"]
        
        # Build response with clear sections
        response = f"""🎉 **Great news! I found the best deal for your trip!**

**💰 Total Cost: ${plan['total_price']:.2f}**

---

✈️ **Flight Details**
- **Airline**: {flight.get('airline', 'Unknown')}
- **Price**: ${flight.get('price', 0):.2f}
- **Departure**: {flight.get('departure_time', 'N/A')}
- **Arrival**: {flight.get('arrival_time', 'N/A')}
- **Stops**: {flight.get('stops', 0)} {'(Non-stop)' if flight.get('stops', 0) == 0 else ''}

🏨 **Hotel Details**
- **Name**: {hotel.get('name', 'Unknown Hotel')}
- **Price**: ${hotel.get('price', 0):.2f}
- **Rating**: {'⭐' * int(hotel.get('rating', 0)) if hotel.get('rating') else 'N/A'}
- **Check-in**: {hotel.get('check_in_time', '15:00')}

---

📋 **Trip Summary**
- **Route**: {params.origin} → {params.destination}
- **Dates**: {params.start_date} to {params.end_date}
- **Arrival Time**: {plan.get('arrival_time', 'N/A')}
- **Buffer to Hotel**: {plan.get('gap_hours', TRAVEL_HOTEL_CHECKIN_GAP_HOURS)} hours

Would you like me to search for different dates or another destination?"""

        return response

    async def _reflection_node(self, state: GraphState) -> dict:
        """
        Reflect on the conversation to determine if further action is needed.
        
        Evaluates whether:
        - The user's request has been fully addressed
        - A follow-up question was asked
        - The conversation should continue or end
        
        Args:
            state: Current graph state with conversation history
        
        Returns:
            Updated state with next_node decision (SUPERVISOR to continue, END to finish)
        """
        if not self.reflection_llm:
            class ShouldContinue(BaseModel):
                should_continue: bool = Field(description="Whether to continue processing")
                reason: str = Field(description="Reason for the decision")
            
            self.reflection_llm = get_llm(streaming=False).with_structured_output(ShouldContinue, strict=True)

        sys_msg = SystemMessage(
            content="""Analyze the conversation to determine if the user's travel request has been addressed.

Set should_continue to TRUE if:
- The user asked a follow-up question
- More information is needed
- The user wants to search again with different criteria

Set should_continue to FALSE if:
- A travel plan was successfully provided
- The user received the information they asked for
- The conversation has reached a natural end"""
        )

        response = await self.reflection_llm.ainvoke([sys_msg] + state["messages"])
        
        if response is None:
            logger.warning("Reflection returned None, ending conversation")
            return {"next_node": END}

        # Check for duplicate messages (conversation loop prevention)
        is_duplicate = (
            len(state["messages"]) > 2 and 
            state["messages"][-1].content == state["messages"][-3].content
        )
        
        should_continue = response.should_continue and not is_duplicate
        next_node = NodeStates.SUPERVISOR if should_continue else END

        logger.info(f"Reflection: continue={should_continue}, reason={response.reason}")
        
        return {"next_node": next_node}

    def _general_response_node(self, state: GraphState) -> dict:
        """
        Handle non-travel queries with helpful guidance.
        
        Provides information about the travel agent's capabilities
        and guides users on how to make travel requests.
        
        Args:
            state: Current graph state
        
        Returns:
            State with helpful response message
        """
        response = """👋 Hello! I'm your Travel Planning Assistant.

I can help you find the **cheapest flight + hotel combinations** for your trips!

**What I can do:**
- 🔍 Search for flights between any two cities
- 🏨 Find hotels at your destination
- 💰 Find the best deal considering total price
- ⏰ Ensure you have enough time between flight arrival and hotel check-in

**To get started, just tell me:**
1. Where you're departing from (e.g., "LAX" or "Los Angeles")
2. Your destination (e.g., "Tokyo" or "NRT")
3. Your travel dates (e.g., "January 15-22, 2026")

**Example:**
"Find me the cheapest trip from New York to Paris, February 1-10, 2026"

How can I help you plan your next adventure?"""

        return {
            "next_node": END,
            "messages": [AIMessage(content=response)],
        }

    async def serve(self, prompt: str) -> str:
        """
        Process a travel request and return the complete response.
        
        This method executes the full graph workflow synchronously,
        waiting for all nodes to complete before returning.
        
        Args:
            prompt: User's travel request string
        
        Returns:
            Final response from the travel agent
        
        Raises:
            ValueError: If prompt is empty
            RuntimeError: If no valid response is generated
        """
        logger.debug(f"Received prompt: {prompt}")
        
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt must be a non-empty string.")
        
        # Execute the graph
        result = await self.graph.ainvoke({
            "messages": [{"role": "user", "content": prompt}],
        }, {"configurable": {"thread_id": uuid.uuid4()}})

        # Extract the final response
        messages = result.get("messages", [])
        if not messages:
            raise RuntimeError("No messages in graph response.")

        # Find the last AI message with content
        for message in reversed(messages):
            if isinstance(message, AIMessage) and message.content.strip():
                return message.content.strip()

        raise RuntimeError("No valid response generated.")

    async def streaming_serve(self, prompt: str):
        """
        Process a travel request and stream responses as they're generated.
        
        This method uses LangGraph's event streaming to provide real-time
        updates as the graph executes through its nodes.
        
        Args:
            prompt: User's travel request string
        
        Yields:
            Response chunks as they're generated
        
        Raises:
            ValueError: If prompt is empty
        """
        logger.debug(f"Received streaming prompt: {prompt}")
        
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt must be a non-empty string.")

        state = {
            "messages": [{"role": "user", "content": prompt}],
        }

        seen_contents = set()
        
        async for event in self.graph.astream_events(
            state, 
            {"configurable": {"thread_id": uuid.uuid4()}}, 
            version="v2"
        ):
            if event["event"] == "on_chain_stream":
                node_name = event.get("name", "")
                data = event.get("data", {})
                
                # Skip reflection node outputs (internal reasoning)
                if node_name == NodeStates.REFLECTION:
                    continue
                
                if "chunk" in data:
                    chunk = data["chunk"]
                    
                    if "messages" in chunk and chunk["messages"]:
                        for message in chunk["messages"]:
                            if isinstance(message, AIMessage) and message.content:
                                content = message.content.strip()
                                
                                # Deduplicate
                                if content in seen_contents:
                                    continue
                                
                                seen_contents.add(content)
                                yield message.content

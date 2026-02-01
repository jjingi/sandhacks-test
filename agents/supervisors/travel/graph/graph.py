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
from datetime import datetime, timedelta

from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph import MessagesState, StateGraph, END
from ioa_observe.sdk.decorators import agent, graph

# Import A2A tools for communicating with Flight and Hotel agents
from agents.supervisors.travel.graph.tools import get_flights_via_a2a, get_hotels_via_a2a
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

        # Step 3: Search for flights and hotels via A2A agents
        logger.info(f"Searching via A2A: {params.origin} -> {params.destination}, {params.start_date} to {params.end_date}")
        
        try:
            # Search for flights via A2A to Flight Agent
            logger.info("Sending A2A request to Flight Search Agent...")
            flights = await get_flights_via_a2a(
                params.origin,
                params.destination,
                params.start_date,
                params.end_date,
            )
            
            if not flights:
                return {"messages": [AIMessage(content=f"I couldn't find any flights from {params.origin} to {params.destination} for those dates. The Flight Agent may be unavailable. Please try again.")]}

            # Search for hotels via A2A to Hotel Agent
            # Use destination_city (city name like "Paris") not destination (airport code like "CDG")
            # Google Hotels needs city names, not airport codes
            hotel_location = params.destination_city or params.destination
            logger.info(f"Sending A2A request to Hotel Search Agent for location: {hotel_location}")
            hotels = await get_hotels_via_a2a(
                hotel_location,
                params.start_date,
                params.end_date,
            )
            
            if not hotels:
                return {"messages": [AIMessage(content=f"I found flights but couldn't find hotels in {hotel_location}. The Hotel Agent may be unavailable.")]}

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
        - Origin city/airport (converted to airport code)
        - Destination city/airport (converted to airport code)
        - Start date
        - End date
        
        Args:
            user_message: Raw user input string
        
        Returns:
            TravelSearchArgs with extracted parameters (airport codes normalized)
        """
        extraction_llm = get_llm(streaming=False).with_structured_output(TravelSearchArgs, strict=False)
        
        # Get current year for date parsing context
        current_year = datetime.now().year
        
        # Prompt the LLM to extract AND convert to airport codes
        prompt = f"""Extract travel search parameters from the user's message.

Current year for reference: {current_year}

User message: {user_message}

IMPORTANT RULES:
- For dates, convert to YYYY-MM-DD format (e.g., "Jan 15" → "{current_year}-01-15")
- If year is not specified, assume {current_year} or {current_year + 1} (whichever makes sense)
- ALWAYS convert origin and destination to 3-letter IATA airport codes:
  * "Los Angeles" or "LA" → "LAX"
  * "New York" or "NYC" → "JFK" (or "EWR" or "LGA")
  * "Tokyo" → "NRT" (Narita) or "HND" (Haneda)
  * "Paris" → "CDG"
  * "London" → "LHR"
  * "San Francisco" or "SF" → "SFO"
  * "Chicago" → "ORD"
  * "Dallas" → "DFW"
  * "Miami" → "MIA"
  * "Seattle" → "SEA"
  * "Boston" → "BOS"
  * "Atlanta" → "ATL"
  * "Denver" → "DEN"
  * "Las Vegas" → "LAS"
  * "Orlando" → "MCO"
  * "Hong Kong" → "HKG"
  * "Singapore" → "SIN"
  * "Sydney" → "SYD"
  * "Dubai" → "DXB"
  * "Seoul" → "ICN"
  * "Bangkok" → "BKK"
  * "Rome" → "FCO"
  * "Amsterdam" → "AMS"
  * "Frankfurt" → "FRA"
  * "Toronto" → "YYZ"
  * "Vancouver" → "YVR"
  * "Mexico City" → "MEX"
  * "Cancun" → "CUN"
- If already an airport code, use it as-is (uppercase)
- Set has_all_params to true ONLY if origin, destination, start_date, AND end_date are all present
- List missing parameters in missing_params field"""

        result = await extraction_llm.ainvoke(prompt)
        logger.info(f"Extracted params: {result}")
        
        # Post-process: Apply fallback city-to-airport mapping if needed
        result = self._normalize_airport_codes(result)
        
        return result
    
    def _normalize_airport_codes(self, params: TravelSearchArgs) -> TravelSearchArgs:
        """
        Normalize city names to airport codes using a fallback mapping.
        
        This handles cases where the LLM returns a city name instead of airport code.
        
        Args:
            params: Extracted travel parameters
            
        Returns:
            Parameters with normalized airport codes
        """
        # Common city name to airport code mapping (fallback)
        city_to_airport = {
            "tokyo": "NRT",
            "paris": "CDG",
            "london": "LHR",
            "new york": "JFK",
            "nyc": "JFK",
            "los angeles": "LAX",
            "la": "LAX",
            "san francisco": "SFO",
            "sf": "SFO",
            "chicago": "ORD",
            "dallas": "DFW",
            "miami": "MIA",
            "seattle": "SEA",
            "boston": "BOS",
            "atlanta": "ATL",
            "denver": "DEN",
            "las vegas": "LAS",
            "orlando": "MCO",
            "hong kong": "HKG",
            "singapore": "SIN",
            "sydney": "SYD",
            "dubai": "DXB",
            "seoul": "ICN",
            "bangkok": "BKK",
            "rome": "FCO",
            "amsterdam": "AMS",
            "frankfurt": "FRA",
            "toronto": "YYZ",
            "vancouver": "YVR",
            "mexico city": "MEX",
            "cancun": "CUN",
            "osaka": "KIX",
            "beijing": "PEK",
            "shanghai": "PVG",
            "mumbai": "BOM",
            "delhi": "DEL",
            "madrid": "MAD",
            "barcelona": "BCN",
            "berlin": "BER",
            "munich": "MUC",
            "zurich": "ZRH",
            "vienna": "VIE",
            "lisbon": "LIS",
            "dublin": "DUB",
            "moscow": "SVO",
            "istanbul": "IST",
            "cairo": "CAI",
            "johannesburg": "JNB",
            "cape town": "CPT",
            "nairobi": "NBO",
            "auckland": "AKL",
            "melbourne": "MEL",
            "brisbane": "BNE",
            "honolulu": "HNL",
            "austin": "AUS",
            "phoenix": "PHX",
            "philadelphia": "PHL",
            "washington": "DCA",
            "washington dc": "DCA",
            "detroit": "DTW",
            "minneapolis": "MSP",
            "portland": "PDX",
            "san diego": "SAN",
            "san jose": "SJC",
            "tampa": "TPA",
            "charlotte": "CLT",
            "houston": "IAH",
        }
        
        # Reverse mapping: airport code to city name (for hotel searches)
        # Used when user provides airport code directly, we need city name for hotels
        airport_to_city = {
            "NRT": "Tokyo, Japan",
            "HND": "Tokyo, Japan",
            "CDG": "Paris, France",
            "ORY": "Paris, France",
            "LHR": "London, UK",
            "LGW": "London, UK",
            "JFK": "New York, NY",
            "EWR": "New York, NY",
            "LGA": "New York, NY",
            "LAX": "Los Angeles, CA",
            "SFO": "San Francisco, CA",
            "ORD": "Chicago, IL",
            "DFW": "Dallas, TX",
            "MIA": "Miami, FL",
            "SEA": "Seattle, WA",
            "BOS": "Boston, MA",
            "ATL": "Atlanta, GA",
            "DEN": "Denver, CO",
            "LAS": "Las Vegas, NV",
            "MCO": "Orlando, FL",
            "HKG": "Hong Kong",
            "SIN": "Singapore",
            "SYD": "Sydney, Australia",
            "DXB": "Dubai, UAE",
            "ICN": "Seoul, South Korea",
            "BKK": "Bangkok, Thailand",
            "FCO": "Rome, Italy",
            "AMS": "Amsterdam, Netherlands",
            "FRA": "Frankfurt, Germany",
            "YYZ": "Toronto, Canada",
            "YVR": "Vancouver, Canada",
            "MEX": "Mexico City, Mexico",
            "CUN": "Cancun, Mexico",
            "KIX": "Osaka, Japan",
            "PEK": "Beijing, China",
            "PVG": "Shanghai, China",
            "BOM": "Mumbai, India",
            "DEL": "Delhi, India",
            "MAD": "Madrid, Spain",
            "BCN": "Barcelona, Spain",
            "BER": "Berlin, Germany",
            "MUC": "Munich, Germany",
            "ZRH": "Zurich, Switzerland",
            "VIE": "Vienna, Austria",
            "LIS": "Lisbon, Portugal",
            "DUB": "Dublin, Ireland",
            "SVO": "Moscow, Russia",
            "IST": "Istanbul, Turkey",
            "CAI": "Cairo, Egypt",
            "JNB": "Johannesburg, South Africa",
            "CPT": "Cape Town, South Africa",
            "NBO": "Nairobi, Kenya",
            "AKL": "Auckland, New Zealand",
            "MEL": "Melbourne, Australia",
            "BNE": "Brisbane, Australia",
            "HNL": "Honolulu, HI",
            "AUS": "Austin, TX",
            "PHX": "Phoenix, AZ",
            "PHL": "Philadelphia, PA",
            "DCA": "Washington, DC",
            "IAD": "Washington, DC",
            "DTW": "Detroit, MI",
            "MSP": "Minneapolis, MN",
            "PDX": "Portland, OR",
            "SAN": "San Diego, CA",
            "SJC": "San Jose, CA",
            "TPA": "Tampa, FL",
            "CLT": "Charlotte, NC",
            "IAH": "Houston, TX",
        }
        
        # Check if origin needs conversion
        if params.origin:
            origin_lower = params.origin.lower().strip()
            original_origin = params.origin.strip()
            
            if origin_lower in city_to_airport:
                # User provided city name - store it and convert to airport code
                params.origin_city = original_origin.title()  # Store original city name
                params.origin = city_to_airport[origin_lower]
                logger.info(f"Converting origin '{original_origin}' to airport code '{params.origin}'")
            else:
                # User provided airport code - look up city name for display
                airport_code = original_origin.upper()
                params.origin = airport_code
                params.origin_city = airport_to_city.get(airport_code, original_origin)
                logger.info(f"Origin is airport code '{airport_code}', city: '{params.origin_city}'")
        
        # Check if destination needs conversion
        if params.destination:
            dest_lower = params.destination.lower().strip()
            original_dest = params.destination.strip()
            
            if dest_lower in city_to_airport:
                # User provided city name - store it and convert to airport code
                params.destination_city = original_dest.title()  # Store original city name for hotel search
                params.destination = city_to_airport[dest_lower]
                logger.info(f"Converting destination '{original_dest}' to airport code '{params.destination}', keeping city '{params.destination_city}' for hotels")
            else:
                # User provided airport code - look up city name for hotel search
                airport_code = original_dest.upper()
                params.destination = airport_code
                params.destination_city = airport_to_city.get(airport_code, original_dest)
                logger.info(f"Destination is airport code '{airport_code}', city for hotels: '{params.destination_city}'")
        
        return params

    def _format_travel_plan(self, plan: dict, params: TravelSearchArgs) -> str:
        """
        Format a travel plan with markdown-style sections: total cost,
        outbound flight, return flight (with full details when available),
        hotel details, and trip summary.
        """
        flight = plan["flight"]
        hotel = plan["hotel"]
        return_flight = flight.get("return_flight")

        outbound_stops = flight.get("stops", 0)
        outbound_stops_text = "(Non-stop)" if outbound_stops == 0 else f"({outbound_stops} stop{'s' if outbound_stops > 1 else ''})"

        overall_rating = hotel.get("overall_rating", 0) or hotel.get("rating", 0) or 0
        rating_display = f"{'⭐' * int(overall_rating)}{'½' if overall_rating and overall_rating % 1 >= 0.5 else ''} ({overall_rating:.1f}/5)" if overall_rating else "N/A"
        location_rating = hotel.get("location_rating", 0) or 0
        location_display = f"{location_rating:.1f}/5" if location_rating else "N/A"

        # Calculate number of nights for hotel total cost
        # Google Hotels returns per-night price, so we multiply by nights
        try:
            start_dt = datetime.strptime(params.start_date.strip()[:10], "%Y-%m-%d")
            end_dt = datetime.strptime(params.end_date.strip()[:10], "%Y-%m-%d")
            nights = max(1, (end_dt - start_dt).days)
        except (ValueError, TypeError, AttributeError):
            nights = 1  # Default to 1 night if date parsing fails

        # Get prices for cost breakdown
        flight_price = flight.get('price') or 0
        hotel_price_per_night = hotel.get('price') or 0
        
        # Calculate total hotel cost = per-night rate × number of nights
        hotel_total_price = hotel_price_per_night * nights
        
        # Calculate correct total price
        total_price = flight_price + hotel_total_price
        
        # Format nights text
        nights_text = f"{nights} night{'s' if nights != 1 else ''}"

        response = f"""🎉 **Great news! I found the best deal for your trip!**

**💰 Total Cost: ${total_price:.2f}**
- ✈️ Flight: ${flight_price:.2f}
- 🏨 Hotel: ${hotel_total_price:.2f} ({nights_text})

---

✈️ **Outbound Flight** ({params.origin} → {params.destination})
- **Airline**: {flight.get('airline', 'Unknown')}
- **Price**: ${flight_price:.2f} (round-trip)
- **Departure**: {flight.get('departure_time', 'N/A')}
- **Arrival**: {flight.get('arrival_time', 'N/A')}
- **Stops**: {outbound_stops} {outbound_stops_text}
"""

        if return_flight:
            return_stops = return_flight.get("stops", 0)
            return_stops_text = "(Non-stop)" if return_stops == 0 else f"({return_stops} stop{'s' if return_stops > 1 else ''})"
            response += f"""
🔙 **Return Flight** ({params.destination} → {params.origin})
- **Airline**: {return_flight.get('airline', flight.get('airline', 'Unknown'))}
- **Departure**: {return_flight.get('departure_time', 'N/A')}
- **Arrival**: {return_flight.get('arrival_time', 'N/A')}
- **Stops**: {return_stops} {return_stops_text}
"""
        else:
            response += f"""
🔙 **Return Flight** ({params.destination} → {params.origin})
- Return flight included in round-trip price
- Specific return times will be shown when booking
"""

        response += f"""
🏨 **Hotel Details**
- **Name**: {hotel.get('name', 'Unknown Hotel')}
- **Price**: ${hotel_price_per_night:.2f}/night × {nights} = ${hotel_total_price:.2f} total
- **Overall Rating**: {rating_display}
- **Location Rating**: {location_display}
- **Check-in**: {hotel.get('check_in_time', '3:00 PM')}

---

📋 **Trip Summary**
- **Route**: {params.origin} → {params.destination} → {params.origin}
- **Dates**: {params.start_date} to {params.end_date}
- **Outbound Arrival**: {plan.get('arrival_time', 'N/A')}
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

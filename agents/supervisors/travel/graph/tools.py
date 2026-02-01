# Copyright AGNTCY Contributors (https://github.com/agntcy)
# SPDX-License-Identifier: Apache-2.0

"""
Travel Supervisor Tools

Tool functions exposed to the LangGraph workflow for searching
flights and hotels, and finding optimal travel plans.

These tools wrap the core travel module functions and add
additional error handling and logging for the supervisor context.
"""

import logging
from typing import Optional

from langchain_core.tools import tool
from ioa_observe.sdk.decorators import tool as ioa_tool_decorator

from agents.travel.serpapi_tools import search_flights, search_hotels
from agents.travel.travel_logic import find_cheapest_plan
from config.config import TRAVEL_HOTEL_CHECKIN_GAP_HOURS

logger = logging.getLogger("lungo.travel.supervisor.tools")


@tool
@ioa_tool_decorator(name="search_travel_flights")
async def search_travel_flights(
    origin: str,
    destination: str,
    outbound_date: str,
    return_date: str,
) -> str:
    """
    Search for flights between two locations.
    
    Use this tool to find available flights for a trip.
    Results are sorted by price (cheapest first).
    
    Args:
        origin: Departure airport code or city (e.g., "LAX", "New York")
        destination: Arrival airport code or city (e.g., "NRT", "Tokyo")
        outbound_date: Departure date in YYYY-MM-DD format
        return_date: Return date in YYYY-MM-DD format
    
    Returns:
        String summary of available flights with prices
    """
    logger.info(f"Tool: Searching flights {origin} -> {destination}, {outbound_date} to {return_date}")
    
    try:
        flights = await search_flights(origin, destination, outbound_date, return_date)
        
        if not flights:
            return f"No flights found from {origin} to {destination} for the specified dates."
        
        # Format results for display
        result_lines = [f"Found {len(flights)} flights from {origin} to {destination}:\n"]
        
        for i, flight in enumerate(flights[:5], 1):  # Show top 5 flights
            result_lines.append(
                f"{i}. {flight.get('airline', 'Unknown')} - ${flight.get('price', 'N/A')}\n"
                f"   Departure: {flight.get('departure_time', 'N/A')}\n"
                f"   Arrival: {flight.get('arrival_time', 'N/A')}\n"
                f"   Stops: {flight.get('stops', 0)}\n"
            )
        
        return "\n".join(result_lines)
        
    except Exception as e:
        logger.error(f"Error searching flights: {e}")
        return f"Error searching flights: {str(e)}"


@tool
@ioa_tool_decorator(name="search_travel_hotels")
async def search_travel_hotels(
    location: str,
    check_in_date: str,
    check_out_date: str,
) -> str:
    """
    Search for hotels at a destination.
    
    Use this tool to find available hotels for accommodation.
    Results are sorted by price (cheapest first).
    
    Args:
        location: City or area to search (e.g., "Tokyo", "Paris")
        check_in_date: Check-in date in YYYY-MM-DD format
        check_out_date: Check-out date in YYYY-MM-DD format
    
    Returns:
        String summary of available hotels with prices
    """
    logger.info(f"Tool: Searching hotels in {location}, {check_in_date} to {check_out_date}")
    
    try:
        hotels = await search_hotels(location, check_in_date, check_out_date)
        
        if not hotels:
            return f"No hotels found in {location} for the specified dates."
        
        # Format results for display
        result_lines = [f"Found {len(hotels)} hotels in {location}:\n"]
        
        for i, hotel in enumerate(hotels[:5], 1):  # Show top 5 hotels
            rating = hotel.get('rating', 0)
            rating_str = f"Rating: {rating}/5" if rating else "Rating: N/A"
            
            result_lines.append(
                f"{i}. {hotel.get('name', 'Unknown Hotel')} - ${hotel.get('price', 'N/A')}\n"
                f"   {rating_str}\n"
                f"   Check-in: {hotel.get('check_in_time', '15:00')}\n"
            )
        
        return "\n".join(result_lines)
        
    except Exception as e:
        logger.error(f"Error searching hotels: {e}")
        return f"Error searching hotels: {str(e)}"


@tool
@ioa_tool_decorator(name="find_best_travel_plan")
async def find_best_travel_plan(
    origin: str,
    destination: str,
    start_date: str,
    end_date: str,
) -> str:
    """
    Find the cheapest flight + hotel combination for a trip.
    
    This tool searches for both flights and hotels, then finds the
    optimal combination considering:
    - Total price (flight + hotel)
    - Timing constraints (hotel check-in must be after flight arrival + buffer)
    
    Args:
        origin: Departure airport code or city
        destination: Arrival airport code or city
        start_date: Trip start date in YYYY-MM-DD format
        end_date: Trip end date in YYYY-MM-DD format
    
    Returns:
        Detailed summary of the best travel plan found
    """
    logger.info(f"Tool: Finding best plan {origin} -> {destination}, {start_date} to {end_date}")
    
    try:
        # Search for flights and hotels
        flights = await search_flights(origin, destination, start_date, end_date)
        hotels = await search_hotels(destination, start_date, end_date)
        
        if not flights:
            return f"No flights found from {origin} to {destination}. Please try different dates or locations."
        
        if not hotels:
            return f"No hotels found in {destination}. Please try different dates or a different area."
        
        # Find cheapest valid combination
        plan = find_cheapest_plan(flights, hotels)
        
        if not plan:
            return (
                f"Could not find a valid flight + hotel combination. "
                f"This may happen if hotel check-in times don't align with flight arrivals. "
                f"Try adjusting your dates or increasing the gap between arrival and check-in."
            )
        
        # Format the result
        flight = plan["flight"]
        hotel = plan["hotel"]
        
        result = f"""
🎉 **Best Travel Plan Found!**

**Total Cost: ${plan['total_price']:.2f}**

✈️ **Flight Details:**
- Airline: {flight.get('airline', 'Unknown')}
- Price: ${flight.get('price', 0):.2f}
- Departure: {flight.get('departure_time', 'N/A')}
- Arrival: {flight.get('arrival_time', 'N/A')}
- Stops: {flight.get('stops', 0)}

🏨 **Hotel Details:**
- Hotel: {hotel.get('name', 'Unknown Hotel')}
- Price: ${hotel.get('price', 0):.2f}
- Rating: {hotel.get('rating', 'N/A')}/5
- Check-in Time: {hotel.get('check_in_time', '15:00')}

📋 **Trip Summary:**
- Route: {origin} → {destination}
- Dates: {start_date} to {end_date}
- Arrival at destination: {plan.get('arrival_time', 'N/A')}
- Buffer time to hotel: {plan.get('gap_hours', TRAVEL_HOTEL_CHECKIN_GAP_HOURS)} hours
"""
        return result.strip()
        
    except Exception as e:
        logger.error(f"Error finding best travel plan: {e}")
        return f"Error finding travel plan: {str(e)}"

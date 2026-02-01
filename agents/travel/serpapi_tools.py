# Copyright AGNTCY Contributors (https://github.com/agntcy)
# SPDX-License-Identifier: Apache-2.0

"""
SerpAPI Tools Module

This module provides functions to search for flights and hotels using the SerpAPI service.
It handles API calls, response parsing, and data normalization.

Key functions:
- search_flights: Search for flights between origin and destination
- search_hotels: Search for hotels at a destination location
"""

import logging
import httpx
from typing import Optional
from datetime import datetime

from config.config import SERPAPI_API_KEY, SERPAPI_BASE_URL

logger = logging.getLogger("lungo.travel.serpapi_tools")


async def search_flights(
    origin: str,
    destination: str,
    outbound_date: str,
    return_date: str,
) -> list[dict]:
    """
    Search for flights using SerpAPI's Google Flights engine.
    
    This function queries SerpAPI for round-trip flights sorted by price (lowest first).
    It extracts the arrival time of the last leg of the outbound flight, which is used
    for hotel check-in timing constraints.
    
    Args:
        origin: Departure airport code (e.g., "LAX", "JFK") or city name
        destination: Arrival airport code or city name
        outbound_date: Departure date in YYYY-MM-DD format
        return_date: Return date in YYYY-MM-DD format
    
    Returns:
        List of flight dictionaries containing:
        - price: Total price in USD
        - departure_time: Outbound flight departure time
        - arrival_time: Outbound flight arrival time (last leg)
        - airline: Primary airline name
        - duration_minutes: Total flight duration
        - stops: Number of stops
        - flights: Full flight legs data from API
    
    Raises:
        Exception: If SerpAPI call fails or returns an error
    
    Example:
        >>> flights = await search_flights("LAX", "NRT", "2026-01-15", "2026-01-22")
        >>> print(flights[0]["price"])  # Cheapest flight price
    """
    logger.info(f"Searching flights: {origin} -> {destination}, {outbound_date} to {return_date}")
    
    # Validate API key is configured
    if not SERPAPI_API_KEY:
        logger.error("SERPAPI_API_KEY is not configured")
        raise ValueError("SerpAPI key is not configured. Please set SERPAPI_API_KEY in your environment.")
    
    # Build SerpAPI request parameters
    # engine=google_flights: Use Google Flights data source
    # type=1: Round trip flight search
    # sort_by=2: Sort results by price (lowest first)
    params = {
        "engine": "google_flights",
        "api_key": SERPAPI_API_KEY,
        "departure_id": origin.upper(),  # Airport codes should be uppercase
        "arrival_id": destination.upper(),
        "outbound_date": outbound_date,
        "return_date": return_date,
        "type": "1",  # 1 = Round trip, 2 = One way
        "sort_by": "2",  # Sort by price
        "currency": "USD",
    }
    
    try:
        # Make async HTTP request to SerpAPI
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(SERPAPI_BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()
        
        # Check for API errors in response
        if "error" in data:
            logger.error(f"SerpAPI error: {data['error']}")
            raise Exception(f"SerpAPI error: {data['error']}")
        
        # Combine best_flights and other_flights for comprehensive results
        # best_flights: SerpAPI's recommended flights
        # other_flights: Additional flight options
        all_flights = []
        best_flights = data.get("best_flights", [])
        other_flights = data.get("other_flights", [])
        
        for flight_group in best_flights + other_flights:
            flight_info = _parse_flight(flight_group)
            if flight_info:
                all_flights.append(flight_info)
        
        logger.info(f"Found {len(all_flights)} flights")
        return all_flights
        
    except httpx.HTTPError as e:
        logger.error(f"HTTP error searching flights: {e}")
        raise Exception(f"Failed to search flights: {e}")


def _parse_flight(flight_group: dict) -> Optional[dict]:
    """
    Parse a flight group from SerpAPI response into a normalized format.
    
    Extracts key information including the arrival time of the LAST leg of the
    outbound journey, which is critical for hotel check-in timing calculations.
    
    Args:
        flight_group: Raw flight data from SerpAPI response
    
    Returns:
        Normalized flight dictionary or None if parsing fails
    """
    try:
        flights = flight_group.get("flights", [])
        if not flights:
            return None
        
        # Get price from flight group
        price = flight_group.get("price", 0)
        
        # First flight is departure, last flight is arrival at destination
        first_flight = flights[0]
        last_flight = flights[-1]  # Last leg of outbound journey
        
        # Extract departure info from first leg
        departure_airport = first_flight.get("departure_airport", {})
        departure_time = departure_airport.get("time", "")
        
        # Extract arrival info from last leg (critical for hotel timing)
        arrival_airport = last_flight.get("arrival_airport", {})
        arrival_time = arrival_airport.get("time", "")
        
        # Get airline and flight details
        airline = first_flight.get("airline", "Unknown")
        total_duration = flight_group.get("total_duration", 0)
        
        return {
            "price": price,
            "departure_time": departure_time,
            "arrival_time": arrival_time,  # Time when traveler arrives at destination
            "airline": airline,
            "duration_minutes": total_duration,
            "stops": len(flights) - 1,  # Number of connections
            "flights": flights,  # Full flight leg data for reference
        }
    except Exception as e:
        logger.warning(f"Failed to parse flight: {e}")
        return None


async def search_hotels(
    location: str,
    check_in_date: str,
    check_out_date: str,
) -> list[dict]:
    """
    Search for hotels using SerpAPI's Google Hotels engine.
    
    This function queries SerpAPI for hotels at the destination, sorted by price.
    If hotel check-in time is not provided by the API, it defaults to 15:00 (3 PM).
    
    Args:
        location: City name or specific location (e.g., "Tokyo", "Paris, France")
        check_in_date: Check-in date in YYYY-MM-DD format
        check_out_date: Check-out date in YYYY-MM-DD format
    
    Returns:
        List of hotel dictionaries containing:
        - name: Hotel name
        - price: Price per night or total price in USD
        - rating: Hotel rating (if available)
        - check_in_time: Expected check-in time (default: "15:00" if not specified)
        - check_in_date: The check-in date
        - amenities: List of hotel amenities
    
    Raises:
        Exception: If SerpAPI call fails or returns an error
    
    Example:
        >>> hotels = await search_hotels("Tokyo", "2026-01-15", "2026-01-22")
        >>> print(hotels[0]["name"], hotels[0]["price"])
    """
    logger.info(f"Searching hotels in {location}, {check_in_date} to {check_out_date}")
    
    # Validate API key is configured
    if not SERPAPI_API_KEY:
        logger.error("SERPAPI_API_KEY is not configured")
        raise ValueError("SerpAPI key is not configured. Please set SERPAPI_API_KEY in your environment.")
    
    # Build SerpAPI request parameters
    # engine=google_hotels: Use Google Hotels data source
    # sort_by=3: Sort by lowest price
    params = {
        "engine": "google_hotels",
        "api_key": SERPAPI_API_KEY,
        "q": location,  # Location query string
        "check_in_date": check_in_date,
        "check_out_date": check_out_date,
        "sort_by": "3",  # Sort by lowest price
        "currency": "USD",
    }
    
    try:
        # Make async HTTP request to SerpAPI
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(SERPAPI_BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()
        
        # Check for API errors in response
        if "error" in data:
            logger.error(f"SerpAPI error: {data['error']}")
            raise Exception(f"SerpAPI error: {data['error']}")
        
        # Parse hotel properties from response
        hotels = []
        properties = data.get("properties", [])
        
        for prop in properties:
            hotel_info = _parse_hotel(prop, check_in_date)
            if hotel_info:
                hotels.append(hotel_info)
        
        logger.info(f"Found {len(hotels)} hotels")
        return hotels
        
    except httpx.HTTPError as e:
        logger.error(f"HTTP error searching hotels: {e}")
        raise Exception(f"Failed to search hotels: {e}")


def _parse_hotel(property_data: dict, check_in_date: str) -> Optional[dict]:
    """
    Parse a hotel property from SerpAPI response into a normalized format.
    
    Note: SerpAPI Google Hotels may not always return check-in time.
    We default to 15:00 (3 PM) which is the standard hotel industry check-in time.
    
    Args:
        property_data: Raw hotel property data from SerpAPI response
        check_in_date: The requested check-in date
    
    Returns:
        Normalized hotel dictionary or None if parsing fails
    """
    try:
        name = property_data.get("name", "Unknown Hotel")
        
        # Extract price - may be in different formats
        # SerpAPI returns either 'rate_per_night' or 'total_rate'
        rate_per_night = property_data.get("rate_per_night", {})
        price = rate_per_night.get("lowest", 0)
        
        # If no rate_per_night, try total_rate
        if not price:
            total_rate = property_data.get("total_rate", {})
            price = total_rate.get("lowest", 0)
        
        # Extract numeric price from string if needed (e.g., "$150" -> 150)
        if isinstance(price, str):
            price = float(price.replace("$", "").replace(",", "").strip() or 0)
        
        rating = property_data.get("overall_rating", 0)
        
        # Check-in time from API (rarely provided)
        # Default to 15:00 (3 PM) - standard hotel industry check-in time
        check_in_time = property_data.get("check_in_time", "15:00")
        
        # Extract amenities for user reference
        amenities = property_data.get("amenities", [])
        
        return {
            "name": name,
            "price": price,
            "rating": rating,
            "check_in_time": check_in_time,
            "check_in_date": check_in_date,
            "amenities": amenities,
        }
    except Exception as e:
        logger.warning(f"Failed to parse hotel: {e}")
        return None

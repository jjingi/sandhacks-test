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
    include_return_flights: bool = True,
) -> list[dict]:
    """
    Search for flights using SerpAPI's Google Flights engine.
    
    This function queries SerpAPI for round-trip flights sorted by price (lowest first).
    It extracts the arrival time of the last leg of the outbound flight, which is used
    for hotel check-in timing constraints.
    
    Optionally fetches return flight options separately to provide complete trip info.
    
    Args:
        origin: Departure airport code (e.g., "LAX", "JFK") or city name
        destination: Arrival airport code or city name
        outbound_date: Departure date in YYYY-MM-DD format
        return_date: Return date in YYYY-MM-DD format
        include_return_flights: If True, fetch return flight options (default: True)
    
    Returns:
        List of flight dictionaries containing:
        - price: Total price in USD (round-trip)
        - departure_time: Outbound flight departure time
        - arrival_time: Outbound flight arrival time (last leg)
        - airline: Primary airline name
        - duration_minutes: Total flight duration
        - stops: Number of stops
        - flights: Full flight legs data from API
        - return_flight: Best matching return flight info (if include_return_flights=True)
    
    Raises:
        Exception: If SerpAPI call fails or returns an error
    
    Example:
        >>> flights = await search_flights("LAX", "NRT", "2026-01-15", "2026-01-22")
        >>> print(flights[0]["price"])  # Cheapest flight price
        >>> print(flights[0]["return_flight"])  # Return flight details
    """
    logger.info(f"Searching flights: {origin} -> {destination}, {outbound_date} to {return_date}")
    
    # Validate API key is configured
    if not SERPAPI_API_KEY:
        logger.error("SERPAPI_API_KEY is not configured")
        raise ValueError("SerpAPI key is not configured. Please set SERPAPI_API_KEY in your environment.")
    
    # Build SerpAPI request parameters for OUTBOUND flights
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
        # Make async HTTP request to SerpAPI for outbound flights
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
        
        logger.info(f"Found {len(all_flights)} outbound flights")
        
        # Fetch return flight options if requested
        # This makes a separate search for the return leg to get actual return times
        if include_return_flights and all_flights:
            return_flights = await _search_return_flights(
                destination, origin, return_date
            )
            
            # Match return flights to outbound flights by airline if possible
            for flight in all_flights:
                flight["return_flight"] = _find_best_return_flight(
                    flight, return_flights
                )
        
        return all_flights
        
    except httpx.HTTPError as e:
        logger.error(f"HTTP error searching flights: {e}")
        raise Exception(f"Failed to search flights: {e}")


async def _search_return_flights(
    origin: str,
    destination: str,
    departure_date: str,
) -> list[dict]:
    """
    Search for one-way return flights.
    
    This is called internally to get return flight options.
    
    Args:
        origin: Return flight departure (original destination)
        destination: Return flight arrival (original origin)
        departure_date: Return date in YYYY-MM-DD format
    
    Returns:
        List of return flight options
    """
    logger.info(f"Searching return flights: {origin} -> {destination}, {departure_date}")
    
    # Build SerpAPI request for one-way return flight
    params = {
        "engine": "google_flights",
        "api_key": SERPAPI_API_KEY,
        "departure_id": origin.upper(),
        "arrival_id": destination.upper(),
        "outbound_date": departure_date,
        "type": "2",  # 2 = One way
        "sort_by": "2",  # Sort by price
        "currency": "USD",
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(SERPAPI_BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()
        
        if "error" in data:
            logger.warning(f"SerpAPI error for return flights: {data['error']}")
            return []
        
        return_flights = []
        best_flights = data.get("best_flights", [])
        other_flights = data.get("other_flights", [])
        
        for flight_group in best_flights + other_flights:
            flight_info = _parse_return_flight(flight_group)
            if flight_info:
                return_flights.append(flight_info)
        
        logger.info(f"Found {len(return_flights)} return flight options")
        return return_flights
        
    except Exception as e:
        logger.warning(f"Failed to fetch return flights: {e}")
        return []


def _parse_return_flight(flight_group: dict) -> Optional[dict]:
    """
    Parse a return flight from SerpAPI response.
    
    Args:
        flight_group: Raw flight data from SerpAPI
    
    Returns:
        Parsed return flight info or None
    """
    try:
        flights = flight_group.get("flights", [])
        if not flights:
            return None
        
        first_flight = flights[0]
        last_flight = flights[-1]
        
        departure_airport = first_flight.get("departure_airport", {})
        arrival_airport = last_flight.get("arrival_airport", {})
        
        return {
            "departure_time": departure_airport.get("time", ""),
            "departure_code": departure_airport.get("id", ""),
            "arrival_time": arrival_airport.get("time", ""),
            "arrival_code": arrival_airport.get("id", ""),
            "airline": first_flight.get("airline", "Unknown"),
            "stops": len(flights) - 1,
            "duration_minutes": flight_group.get("total_duration", 0),
            "price": flight_group.get("price", 0),  # One-way price (for reference)
        }
    except Exception as e:
        logger.warning(f"Failed to parse return flight: {e}")
        return None


def _find_best_return_flight(outbound: dict, return_flights: list[dict]) -> Optional[dict]:
    """
    Find the best matching return flight for an outbound flight.
    
    Prefers return flights with:
    1. Same airline as outbound (for consistency)
    2. Similar number of stops
    3. Reasonable departure time
    
    Args:
        outbound: The outbound flight
        return_flights: Available return flight options
    
    Returns:
        Best matching return flight or None
    """
    if not return_flights:
        return None
    
    outbound_airline = outbound.get("airline", "").lower()
    outbound_stops = outbound.get("stops", 0)
    
    # Score each return flight
    scored_flights = []
    for rf in return_flights:
        score = 0
        
        # Prefer same airline
        if rf.get("airline", "").lower() == outbound_airline:
            score += 10
        
        # Prefer similar number of stops
        stops_diff = abs(rf.get("stops", 0) - outbound_stops)
        score -= stops_diff * 2
        
        # Prefer non-stop if outbound is non-stop
        if outbound_stops == 0 and rf.get("stops", 0) == 0:
            score += 5
        
        scored_flights.append((score, rf))
    
    # Sort by score (highest first) and return best match
    scored_flights.sort(key=lambda x: x[0], reverse=True)
    return scored_flights[0][1] if scored_flights else None


def _parse_flight(flight_group: dict) -> Optional[dict]:
    """
    Parse a flight group from SerpAPI response into a normalized format.
    
    Extracts key information including:
    - Outbound flight: departure/arrival times for going TO destination
    - Return flight: departure/arrival times for coming BACK home
    
    The arrival time of the outbound flight is critical for hotel check-in timing.
    
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
        
        # Extract OUTBOUND flight info
        departure_airport = first_flight.get("departure_airport", {})
        departure_time = departure_airport.get("time", "")
        departure_code = departure_airport.get("id", "")
        
        arrival_airport = last_flight.get("arrival_airport", {})
        arrival_time = arrival_airport.get("time", "")
        arrival_code = arrival_airport.get("id", "")
        
        # Get airline and flight details
        airline = first_flight.get("airline", "Unknown")
        total_duration = flight_group.get("total_duration", 0)
        
        # Extract RETURN flight info if available
        # SerpAPI includes return flights in "return_flights" for round trips
        return_flights = flight_group.get("return_flights", [])
        return_flight_info = None
        
        if return_flights:
            # Parse return flight details
            return_first = return_flights[0]
            return_last = return_flights[-1]
            
            return_departure_airport = return_first.get("departure_airport", {})
            return_arrival_airport = return_last.get("arrival_airport", {})
            
            return_flight_info = {
                "departure_time": return_departure_airport.get("time", ""),
                "departure_code": return_departure_airport.get("id", ""),
                "arrival_time": return_arrival_airport.get("time", ""),
                "arrival_code": return_arrival_airport.get("id", ""),
                "airline": return_first.get("airline", airline),  # May be different airline
                "stops": len(return_flights) - 1,
                "duration_minutes": flight_group.get("return_duration", 0),
            }
        
        return {
            "price": price,
            # Outbound flight details
            "departure_time": departure_time,
            "departure_code": departure_code,
            "arrival_time": arrival_time,  # Time when traveler arrives at destination
            "arrival_code": arrival_code,
            "airline": airline,
            "duration_minutes": total_duration,
            "stops": len(flights) - 1,  # Number of connections
            "flights": flights,  # Full flight leg data for reference
            # Return flight details (None if one-way or not available)
            "return_flight": return_flight_info,
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
            # Parse hotel info - price is as-is from API (per-night or total depending on API)
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
    
    Extracts various rating categories:
    - overall_rating: General hotel rating (1-5 scale)
    - location_rating: Rating for hotel location
    - Other category ratings (service, rooms, etc.) if available
    
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
        
        # Extract overall rating (1-5 scale)
        overall_rating = property_data.get("overall_rating", 0)
        if overall_rating is None:
            overall_rating = 0
        
        # Extract location rating from ratings breakdown
        # SerpAPI may return ratings as a list of {name: "Location", rating: 4.5} objects
        # or in a separate "location_rating" field
        location_rating = 0
        ratings_breakdown = property_data.get("ratings", [])
        
        if isinstance(ratings_breakdown, list):
            for rating_item in ratings_breakdown:
                if isinstance(rating_item, dict):
                    rating_name = rating_item.get("name", "").lower()
                    if "location" in rating_name:
                        location_rating = rating_item.get("rating", 0) or 0
                        break
        
        # Also check for direct location_rating field
        if not location_rating:
            location_rating = property_data.get("location_rating", 0) or 0
        
        # Check-in time from API (rarely provided)
        # Default to 15:00 (3 PM) - standard hotel industry check-in time
        check_in_time = property_data.get("check_in_time", "15:00")
        
        # Extract amenities for user reference
        amenities = property_data.get("amenities", [])
        
        # Extract hotel class/stars if available
        hotel_class = property_data.get("hotel_class", 0)
        
        return {
            "name": name,
            "price": price,
            "rating": overall_rating,  # Overall rating (for backward compatibility)
            "overall_rating": overall_rating,  # Explicit overall rating
            "location_rating": location_rating,  # Location-specific rating
            "hotel_class": hotel_class,  # Star rating (e.g., 3, 4, 5 stars)
            "check_in_time": check_in_time,
            "check_in_date": check_in_date,
            "amenities": amenities,
        }
    except Exception as e:
        logger.warning(f"Failed to parse hotel: {e}")
        return None

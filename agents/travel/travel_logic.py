# Copyright AGNTCY Contributors (https://github.com/agntcy)
# SPDX-License-Identifier: Apache-2.0

"""
Travel Logic Module

This module contains the business logic for finding optimal travel plans.
It handles timing constraints between flights and hotels, ensuring the traveler
has sufficient time to get from the airport to their hotel.

Key functions:
- extract_arrival_datetime: Parse flight arrival time into datetime
- filter_valid_hotels: Filter hotels that meet timing constraints
- find_cheapest_plan: Find the cheapest flight + hotel combination
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from config.config import TRAVEL_HOTEL_CHECKIN_GAP_HOURS

logger = logging.getLogger("lungo.travel.travel_logic")


def extract_arrival_datetime(flight: dict) -> Optional[datetime]:
    """
    Extract the arrival datetime from a flight's last leg.
    
    The arrival time represents when the traveler actually arrives at their
    destination, which is used to calculate if they can make hotel check-in.
    
    Supported time formats:
    - "YYYY-MM-DD HH:MM" (e.g., "2026-01-15 18:30")
    - "HH:MM" (time only, requires date inference from flight data)
    
    Args:
        flight: Flight dictionary containing arrival_time
    
    Returns:
        datetime object representing arrival time, or None if parsing fails
    
    Example:
        >>> flight = {"arrival_time": "2026-01-15 18:30"}
        >>> arrival = extract_arrival_datetime(flight)
        >>> print(arrival)  # datetime(2026, 1, 15, 18, 30)
    """
    arrival_time_str = flight.get("arrival_time", "")
    
    if not arrival_time_str:
        logger.warning("No arrival time found in flight data")
        return None
    
    # Try parsing various time formats
    formats_to_try = [
        "%Y-%m-%d %H:%M",     # Full datetime: "2026-01-15 18:30"
        "%Y-%m-%dT%H:%M",     # ISO format: "2026-01-15T18:30"
        "%Y-%m-%d %H:%M:%S",  # With seconds: "2026-01-15 18:30:00"
    ]
    
    for fmt in formats_to_try:
        try:
            return datetime.strptime(arrival_time_str, fmt)
        except ValueError:
            continue
    
    logger.warning(f"Could not parse arrival time: {arrival_time_str}")
    return None


def filter_valid_hotels(
    hotels: list[dict],
    flight_arrival: datetime,
    gap_hours: Optional[int] = None,
) -> list[dict]:
    """
    Filter hotels that allow check-in after the traveler arrives from their flight.
    
    This ensures the traveler has enough time (gap_hours) to:
    - Deplane and go through customs/immigration
    - Collect baggage
    - Travel from airport to hotel
    - Arrive at hotel in time for check-in
    
    Timing constraint:
        Hotels allow check-in ANYTIME AFTER their stated check-in time.
        So if check-in starts at 3 PM and traveler arrives at 5 PM + 2h gap = 7 PM,
        that's valid because 3 PM has already passed.
        
        Valid condition: hotel_check_in_time <= traveler_arrival_at_hotel
        AND traveler_arrival_at_hotel <= reasonable_cutoff (midnight)
    
    Args:
        hotels: List of hotel dictionaries with check_in_date and check_in_time
        flight_arrival: datetime when flight arrives at destination
        gap_hours: Minimum hours between flight arrival and hotel check-in.
                   Defaults to TRAVEL_HOTEL_CHECKIN_GAP_HOURS from config.
    
    Returns:
        List of hotels that meet the timing constraint
    
    Example:
        >>> flight_arrival = datetime(2026, 1, 15, 18, 30)  # 6:30 PM arrival
        >>> hotels = [{"check_in_time": "15:00", ...}, {"check_in_time": "20:00", ...}]
        >>> valid = filter_valid_hotels(hotels, flight_arrival, gap_hours=2)
        >>> # Hotel with 15:00 check-in is valid (traveler arrives at hotel ~8:30 PM, check-in started at 3 PM)
        >>> # Hotel with 20:00 check-in is valid (traveler arrives at hotel ~8:30 PM, check-in started at 8 PM)
    """
    if gap_hours is None:
        gap_hours = TRAVEL_HOTEL_CHECKIN_GAP_HOURS
    
    # Calculate when traveler actually arrives at hotel
    traveler_hotel_arrival = flight_arrival + timedelta(hours=gap_hours)
    
    # Reasonable cutoff - traveler should arrive at hotel before midnight
    midnight_cutoff = datetime.combine(flight_arrival.date(), datetime.strptime("23:59", "%H:%M").time())
    
    logger.info(
        f"Filtering hotels: flight arrives {flight_arrival.strftime('%Y-%m-%d %H:%M')}, "
        f"traveler reaches hotel by {traveler_hotel_arrival.strftime('%Y-%m-%d %H:%M')} (gap: {gap_hours}h)"
    )
    
    valid_hotels = []
    
    for hotel in hotels:
        hotel_checkin_datetime = _get_hotel_checkin_datetime(hotel, flight_arrival)
        
        if hotel_checkin_datetime is None:
            # If we can't determine check-in time, include it anyway (be permissive)
            logger.warning(f"Could not determine check-in time for hotel: {hotel.get('name')}, including anyway")
            valid_hotels.append(hotel)
            continue
        
        # Check if:
        # 1. Hotel check-in has started by the time traveler arrives (check-in time <= traveler arrival)
        # 2. Traveler arrives before midnight (reasonable cutoff)
        # 
        # Hotels allow check-in ANYTIME AFTER the stated check-in time.
        # So if hotel says "check-in: 3 PM" and traveler arrives at 8 PM, that's valid.
        checkin_has_started = hotel_checkin_datetime.time() <= traveler_hotel_arrival.time()
        arrives_before_midnight = traveler_hotel_arrival <= midnight_cutoff
        
        # Also allow same-day arrivals where traveler arrives after check-in time
        same_day_valid = (
            flight_arrival.date() == hotel_checkin_datetime.date() and
            traveler_hotel_arrival.time() >= hotel_checkin_datetime.time()
        )
        
        if (checkin_has_started and arrives_before_midnight) or same_day_valid:
            valid_hotels.append(hotel)
            logger.debug(f"Hotel '{hotel.get('name')}' is valid (check-in starts: {hotel_checkin_datetime.time()}, traveler arrives: {traveler_hotel_arrival.time()})")
        else:
            logger.debug(
                f"Hotel '{hotel.get('name')}' excluded - check-in starts {hotel_checkin_datetime.time()}, "
                f"traveler would arrive at {traveler_hotel_arrival.time()}"
            )
    
    logger.info(f"Filtered {len(valid_hotels)} valid hotels from {len(hotels)} total")
    return valid_hotels


def _get_hotel_checkin_datetime(hotel: dict, reference_date: datetime) -> Optional[datetime]:
    """
    Convert hotel check-in date and time into a datetime object.
    
    If check_in_date is provided, use it. Otherwise, use the reference_date
    (typically the flight arrival date) as the check-in date.
    
    Default check-in time is 15:00 (3 PM) if not specified.
    
    Args:
        hotel: Hotel dictionary with check_in_date and check_in_time
        reference_date: Date to use if hotel check_in_date is not available
    
    Returns:
        datetime for hotel check-in, or None if parsing fails
    """
    # Get check-in date - use hotel's date or flight arrival date
    check_in_date_str = hotel.get("check_in_date", "")
    
    if check_in_date_str:
        try:
            check_in_date = datetime.strptime(check_in_date_str, "%Y-%m-%d").date()
        except ValueError:
            check_in_date = reference_date.date()
    else:
        check_in_date = reference_date.date()
    
    # Get check-in time - default to 15:00 (3 PM) if not specified
    check_in_time_str = hotel.get("check_in_time", "15:00")
    
    try:
        # Parse time string (e.g., "15:00" or "3:00 PM")
        if "PM" in check_in_time_str.upper() or "AM" in check_in_time_str.upper():
            check_in_time = datetime.strptime(check_in_time_str, "%I:%M %p").time()
        else:
            check_in_time = datetime.strptime(check_in_time_str, "%H:%M").time()
    except ValueError:
        # Default to 3 PM if parsing fails
        check_in_time = datetime.strptime("15:00", "%H:%M").time()
    
    # Combine date and time
    return datetime.combine(check_in_date, check_in_time)


def find_cheapest_plan(
    flights: list[dict],
    hotels: list[dict],
    gap_hours: Optional[int] = None,
) -> Optional[dict]:
    """
    Find the cheapest flight + hotel combination that meets timing constraints.
    
    This function iterates through all flight options, filters hotels that are
    valid for each flight's arrival time, and finds the combination with the
    lowest total price (flight + hotel).
    
    Algorithm:
    1. For each flight, extract arrival datetime
    2. Filter hotels that allow check-in after arrival + gap_hours
    3. Find cheapest valid hotel for that flight
    4. Track minimum total cost across all combinations
    5. Return the best plan
    
    Args:
        flights: List of flight options from search_flights()
        hotels: List of hotel options from search_hotels()
        gap_hours: Minimum hours between flight arrival and hotel check-in.
                   Defaults to TRAVEL_HOTEL_CHECKIN_GAP_HOURS from config.
    
    Returns:
        Dictionary containing the best travel plan:
        - flight: Selected flight details
        - hotel: Selected hotel details
        - total_price: Combined flight + hotel price
        - gap_hours: The timing gap used for filtering
        - arrival_time: When traveler arrives at destination
        
        Returns None if no valid combination is found.
    
    Example:
        >>> flights = await search_flights("LAX", "NRT", "2026-01-15", "2026-01-22")
        >>> hotels = await search_hotels("Tokyo", "2026-01-15", "2026-01-22")
        >>> plan = find_cheapest_plan(flights, hotels)
        >>> if plan:
        ...     print(f"Best deal: ${plan['total_price']}")
        ...     print(f"Flight: {plan['flight']['airline']} - ${plan['flight']['price']}")
        ...     print(f"Hotel: {plan['hotel']['name']} - ${plan['hotel']['price']}")
    """
    if gap_hours is None:
        gap_hours = TRAVEL_HOTEL_CHECKIN_GAP_HOURS
    
    logger.info(f"Finding cheapest plan from {len(flights)} flights and {len(hotels)} hotels")
    
    if not flights:
        logger.warning("No flights provided")
        return None
    
    if not hotels:
        logger.warning("No hotels provided")
        return None
    
    best_plan = None
    best_total_price = float('inf')
    
    for flight in flights:
        # Get when traveler arrives at destination
        arrival_datetime = extract_arrival_datetime(flight)
        
        if arrival_datetime is None:
            logger.warning(f"Skipping flight with unparseable arrival time")
            continue
        
        # Filter hotels that work with this flight's arrival time
        valid_hotels = filter_valid_hotels(hotels, arrival_datetime, gap_hours)
        
        if not valid_hotels:
            logger.debug(f"No valid hotels for flight arriving at {arrival_datetime}")
            continue
        
        # Find cheapest valid hotel for this flight
        for hotel in valid_hotels:
            flight_price = flight.get("price", 0)
            hotel_price = hotel.get("price", 0)
            total_price = flight_price + hotel_price
            
            if total_price < best_total_price:
                best_total_price = total_price
                best_plan = {
                    "flight": flight,
                    "hotel": hotel,
                    "total_price": total_price,
                    "gap_hours": gap_hours,
                    "arrival_time": arrival_datetime.strftime("%Y-%m-%d %H:%M"),
                }
                logger.debug(f"New best plan: ${total_price} (flight: ${flight_price}, hotel: ${hotel_price})")
    
    if best_plan:
        logger.info(
            f"Found cheapest plan: ${best_plan['total_price']} total "
            f"(flight: ${best_plan['flight']['price']}, hotel: ${best_plan['hotel']['price']})"
        )
    else:
        logger.warning("No valid flight + hotel combination found")
    
    return best_plan

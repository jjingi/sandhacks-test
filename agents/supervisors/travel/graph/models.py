# Copyright AGNTCY Contributors (https://github.com/agntcy)
# SPDX-License-Identifier: Apache-2.0

"""
Travel Supervisor Models

Pydantic models for structured data extraction and validation.
These models are used with LLM structured output to ensure
proper parsing of user travel requests.
"""

from pydantic import BaseModel, Field
from typing import Optional


class TravelSearchArgs(BaseModel):
    """
    Arguments extracted from user input for travel search.
    
    Used with LLM structured output to parse natural language
    trip requests into structured parameters.
    
    Attributes:
        origin: Departure city or airport code (e.g., "LAX", "New York")
        destination: Arrival city or airport code (e.g., "NRT", "Tokyo")
        start_date: Trip start date in YYYY-MM-DD format
        end_date: Trip end date in YYYY-MM-DD format
        has_all_params: Whether all required parameters were extracted
        missing_params: Description of any missing parameters
    
    Example user input: "Find me flights from LAX to Tokyo, Jan 15-22, 2026"
    Extracted: origin="LAX", destination="Tokyo", start_date="2026-01-15", end_date="2026-01-22"
    """
    origin: Optional[str] = Field(
        default=None,
        description="Departure city name or airport code (e.g., 'LAX', 'New York', 'JFK')"
    )
    destination: Optional[str] = Field(
        default=None,
        description="Arrival city name or airport code (e.g., 'NRT', 'Tokyo', 'Paris')"
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Trip start/departure date in YYYY-MM-DD format"
    )
    end_date: Optional[str] = Field(
        default=None,
        description="Trip end/return date in YYYY-MM-DD format"
    )
    has_all_params: bool = Field(
        default=False,
        description="True if all required parameters (origin, destination, start_date, end_date) were extracted"
    )
    missing_params: str = Field(
        default="",
        description="Comma-separated list of missing parameters, if any"
    )


class TravelPlan(BaseModel):
    """
    Represents a complete travel plan with flight and hotel details.
    
    Used to structure the response returned to the user after
    finding the optimal flight + hotel combination.
    
    Attributes:
        flight_price: Cost of the flight in USD
        flight_airline: Airline operating the flight
        flight_departure: Departure datetime string
        flight_arrival: Arrival datetime string
        flight_stops: Number of layovers/stops
        hotel_name: Name of the selected hotel
        hotel_price: Cost of the hotel stay in USD
        hotel_rating: Hotel star rating
        total_price: Combined flight + hotel cost
        check_in_gap_hours: Hours between flight arrival and hotel check-in
    """
    flight_price: float = Field(description="Flight price in USD")
    flight_airline: str = Field(description="Airline name")
    flight_departure: str = Field(description="Departure datetime")
    flight_arrival: str = Field(description="Arrival datetime")
    flight_stops: int = Field(description="Number of stops/layovers")
    hotel_name: str = Field(description="Hotel name")
    hotel_price: float = Field(description="Hotel price in USD")
    hotel_rating: float = Field(default=0, description="Hotel rating")
    total_price: float = Field(description="Total trip cost in USD")
    check_in_gap_hours: int = Field(description="Gap between arrival and check-in")

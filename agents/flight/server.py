# Copyright AGNTCY Contributors (https://github.com/agntcy)
# SPDX-License-Identifier: Apache-2.0

"""
Flight Search Agent Server

A2A server that handles flight search requests from other agents.
Runs as a FastAPI server with A2A protocol support.
"""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from agntcy_app_sdk.factory import AgntcyFactory
from agntcy_app_sdk.semantic.a2a.protocol import A2AProtocol

from agents.flight.card import AGENT_CARD
from agents.flight.agent import FlightSearchAgent
from config.config import (
    DEFAULT_MESSAGE_TRANSPORT,
    TRANSPORT_SERVER_ENDPOINT,
    ENABLE_HTTP,
)
from config.logging_config import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger("lungo.flight.server")
load_dotenv()

# Global instances
factory = None
a2a_server = None
flight_agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Starts the A2A server on startup and cleans up on shutdown.
    """
    global factory, a2a_server, flight_agent
    
    logger.info("Starting Flight Search Agent server...")
    
    # Initialize the flight agent
    flight_agent = FlightSearchAgent()
    
    # Create the Agntcy factory
    factory = AgntcyFactory("lungo.flight_agent", enable_tracing=True)
    
    # Create transport
    transport = factory.create_transport(
        DEFAULT_MESSAGE_TRANSPORT,
        endpoint=TRANSPORT_SERVER_ENDPOINT,
        name="default/default/flight_agent",
    )
    
    # Create A2A server
    a2a_server = await factory.create_server(
        "A2A",
        agent_topic=A2AProtocol.create_agent_topic(AGENT_CARD),
        transport=transport,
        agent_card=AGENT_CARD,
    )
    
    # Register message handler
    async def handle_message(message: str) -> str:
        """Handle incoming A2A messages."""
        logger.info(f"Received A2A message: {message}")
        result = await flight_agent.ainvoke(message)
        logger.info(f"Sending response: {result[:100]}...")
        return result
    
    a2a_server.register_handler(handle_message)
    
    # Start the A2A server
    await a2a_server.start()
    logger.info(f"Flight Agent A2A server started on transport: {DEFAULT_MESSAGE_TRANSPORT}")
    
    yield
    
    # Cleanup
    logger.info("Shutting down Flight Search Agent server...")
    if a2a_server:
        await a2a_server.stop()


# Create FastAPI app
app = FastAPI(
    title="Flight Search Agent",
    description="A2A agent for searching flights using SerpAPI",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "agent": "flight_search"}


@app.get("/.well-known/agent.json")
async def get_agent_card():
    """Return the A2A agent card."""
    return AGENT_CARD.model_dump()


if __name__ == "__main__":
    port = int(os.getenv("FLIGHT_AGENT_PORT", "9001"))
    host = os.getenv("FLIGHT_AGENT_HOST", "0.0.0.0")
    
    logger.info(f"Starting Flight Agent on {host}:{port}")
    uvicorn.run(
        "agents.flight.server:app",
        host=host,
        port=port,
        reload=True,
    )

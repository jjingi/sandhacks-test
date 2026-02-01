# Copyright AGNTCY Contributors (https://github.com/agntcy)
# SPDX-License-Identifier: Apache-2.0

"""
Hotel Search Agent Server

A2A server that handles hotel search requests from other agents.
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

from agents.hotel.card import AGENT_CARD
from agents.hotel.agent import HotelSearchAgent
from config.config import (
    DEFAULT_MESSAGE_TRANSPORT,
    TRANSPORT_SERVER_ENDPOINT,
    ENABLE_HTTP,
)
from config.logging_config import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger("lungo.hotel.server")
load_dotenv()

# Global instances
factory = None
a2a_server = None
hotel_agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Starts the A2A server on startup and cleans up on shutdown.
    """
    global factory, a2a_server, hotel_agent
    
    logger.info("Starting Hotel Search Agent server...")
    
    # Initialize the hotel agent
    hotel_agent = HotelSearchAgent()
    
    # Create the Agntcy factory
    factory = AgntcyFactory("lungo.hotel_agent", enable_tracing=True)
    
    # Create transport
    transport = factory.create_transport(
        DEFAULT_MESSAGE_TRANSPORT,
        endpoint=TRANSPORT_SERVER_ENDPOINT,
        name="default/default/hotel_agent",
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
        result = await hotel_agent.ainvoke(message)
        logger.info(f"Sending response: {result[:100]}...")
        return result
    
    a2a_server.register_handler(handle_message)
    
    # Start the A2A server
    await a2a_server.start()
    logger.info(f"Hotel Agent A2A server started on transport: {DEFAULT_MESSAGE_TRANSPORT}")
    
    yield
    
    # Cleanup
    logger.info("Shutting down Hotel Search Agent server...")
    if a2a_server:
        await a2a_server.stop()


# Create FastAPI app
app = FastAPI(
    title="Hotel Search Agent",
    description="A2A agent for searching hotels using SerpAPI",
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
    return {"status": "ok", "agent": "hotel_search"}


@app.get("/.well-known/agent.json")
async def get_agent_card():
    """Return the A2A agent card."""
    return AGENT_CARD.model_dump()


if __name__ == "__main__":
    port = int(os.getenv("HOTEL_AGENT_PORT", "9002"))
    host = os.getenv("HOTEL_AGENT_HOST", "0.0.0.0")
    
    logger.info(f"Starting Hotel Agent on {host}:{port}")
    uvicorn.run(
        "agents.hotel.server:app",
        host=host,
        port=port,
        reload=True,
    )

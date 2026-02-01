/**
 * Copyright AGNTCY Contributors (https://github.com/agntcy)
 * SPDX-License-Identifier: Apache-2.0
 * 
 * Pattern Utilities for Travel Agent
 * 
 * This module provides pattern-based configuration for the Travel Planning Agent.
 * The travel agent uses a simplified architecture compared to the original coffee
 * farm demo - it only needs a supervisor that calls external APIs (SerpAPI).
 **/

export const PATTERNS = {
  // Travel agent pattern - searches for flights and hotels
  TRAVEL_SEARCH: "travel_search",
  // Streaming travel search with real-time updates
  TRAVEL_SEARCH_STREAMING: "travel_search_streaming",
  // Legacy patterns (kept for backward compatibility, but not used)
  PUBLISH_SUBSCRIBE: "publish_subscribe",
  PUBLISH_SUBSCRIBE_STREAMING: "publish_subscribe_streaming",
  GROUP_COMMUNICATION: "group_communication",
} as const

export type PatternType = (typeof PATTERNS)[keyof typeof PATTERNS]

/**
 * Check if the pattern requires group communication (not used for travel agent)
 */
export const isGroupCommunication = (pattern?: string): boolean => {
  // Travel agent doesn't use group communication
  return false
}

/**
 * Determine if retries should be enabled for a pattern
 */
export const shouldEnableRetries = (pattern?: string): boolean => {
  return isGroupCommunication(pattern)
}

/**
 * Get the API URL for the travel supervisor
 * The travel agent runs on port 8000 by default
 */
export const getApiUrlForPattern = (pattern?: string): string => {
  const DEFAULT_TRAVEL_API_URL = "http://127.0.0.1:8000"
  const TRAVEL_APP_API_URL =
    import.meta.env.VITE_EXCHANGE_APP_API_URL || DEFAULT_TRAVEL_API_URL

  // All patterns use the travel supervisor API URL (port 8000)
  // This includes legacy patterns that are mapped to travel functionality
  return TRAVEL_APP_API_URL
}

/**
 * Check if pattern supports Server-Sent Events
 */
export const supportsSSE = (pattern?: string): boolean => {
  return false
}

/**
 * Get the streaming endpoint URL for a pattern
 */
export const getStreamingEndpointForPattern = (pattern?: string): string => {
  // All streaming patterns use the same travel supervisor endpoint
  return `${getApiUrlForPattern(pattern)}/agent/prompt/stream`
}

/**
 * Check if a pattern uses streaming responses
 */
export const isStreamingPattern = (pattern?: string): boolean => {
  return (
    pattern === PATTERNS.TRAVEL_SEARCH_STREAMING ||
    pattern === PATTERNS.PUBLISH_SUBSCRIBE_STREAMING ||
    pattern === PATTERNS.GROUP_COMMUNICATION
  )
}

/**
 * Check if pattern supports transport updates (NATS/SLIM switching)
 */
export const supportsTransportUpdates = (pattern?: string): boolean => {
  return (
    pattern === PATTERNS.TRAVEL_SEARCH ||
    pattern === PATTERNS.TRAVEL_SEARCH_STREAMING
  )
}

/**
 * Get a human-readable display name for a pattern
 */
export const getPatternDisplayName = (pattern?: string): string => {
  switch (pattern) {
    case PATTERNS.TRAVEL_SEARCH:
      return "Travel Search"
    case PATTERNS.TRAVEL_SEARCH_STREAMING:
      return "Travel Search: Streaming"
    case PATTERNS.PUBLISH_SUBSCRIBE:
      return "Travel Search"
    case PATTERNS.PUBLISH_SUBSCRIBE_STREAMING:
      return "Travel Search: Streaming"
    case PATTERNS.GROUP_COMMUNICATION:
      return "Travel Search: Streaming"
    default:
      return "Travel Agent"
  }
}

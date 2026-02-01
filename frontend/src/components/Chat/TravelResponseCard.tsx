/**
 * Copyright AGNTCY Contributors (https://github.com/agntcy)
 * SPDX-License-Identifier: Apache-2.0
 * 
 * Beautiful card-based rendering for travel agent responses
 **/

import React from 'react'
import { Plane, Hotel, Calendar, DollarSign, Clock, MapPin, Star, ArrowRight } from 'lucide-react'

interface TravelResponseCardProps {
  content: string
}

// Parse the response into structured sections
const parseResponse = (content: string) => {
  const sections: {
    intro?: string
    totalCost?: string
    flightCost?: string
    hotelCost?: string
    outboundFlight?: Record<string, string>
    returnFlight?: Record<string, string>
    hotel?: Record<string, string>
    tripSummary?: string[]
  } = {}

  const lines = content.split('\n')
  let currentSection = ''
  let tripSummaryLines: string[] = []

  for (const line of lines) {
    const trimmed = line.trim()
    
    // Skip empty lines and separators
    if (!trimmed || trimmed === '---') continue

    // Detect sections
    if (trimmed.includes('Great news') || trimmed.includes('found the best')) {
      sections.intro = trimmed.replace(/\*\*/g, '').replace(/🎉/g, '').trim()
      continue
    }

    if (trimmed.includes('Total Cost:')) {
      sections.totalCost = trimmed.match(/\$[\d,.]+/)?.[0] || ''
      continue
    }

    if (trimmed.includes('Flight:') && trimmed.includes('$') && !trimmed.includes('Flight**')) {
      sections.flightCost = trimmed.match(/\$[\d,.]+/)?.[0] || ''
      continue
    }

    if (trimmed.includes('Hotel:') && trimmed.includes('$') && !trimmed.includes('Hotel**')) {
      sections.hotelCost = trimmed.match(/\$[\d,.]+/)?.[0] || ''
      continue
    }

    if (trimmed.includes('Outbound Flight')) {
      currentSection = 'outbound'
      sections.outboundFlight = {}
      continue
    }

    if (trimmed.includes('Return Flight')) {
      currentSection = 'return'
      sections.returnFlight = {}
      continue
    }

    if (trimmed.includes('Hotel Details')) {
      currentSection = 'hotel'
      sections.hotel = {}
      continue
    }

    if (trimmed.includes('Trip Summary')) {
      currentSection = 'summary'
      tripSummaryLines = []
      continue
    }

    // Parse section content
    if (currentSection === 'outbound' && sections.outboundFlight) {
      parseFlightLine(trimmed, sections.outboundFlight)
    } else if (currentSection === 'return' && sections.returnFlight) {
      parseFlightLine(trimmed, sections.returnFlight)
    } else if (currentSection === 'hotel' && sections.hotel) {
      parseHotelLine(trimmed, sections.hotel)
    } else if (currentSection === 'summary') {
      const cleaned = trimmed.replace(/^-\s*/, '').replace(/\*\*/g, '').trim()
      if (cleaned) tripSummaryLines.push(cleaned)
    }
  }

  if (tripSummaryLines.length > 0) {
    sections.tripSummary = tripSummaryLines
  }

  return sections
}

// Helper to extract value after the first colon, preserving any colons in the value (like times)
const extractAfterFirstColon = (str: string): string => {
  const colonIndex = str.indexOf(':')
  if (colonIndex === -1) return ''
  return str.substring(colonIndex + 1).trim()
}

// Format date from YYYY-MM-DD to MM-DD-YYYY, preserving time if present
const formatDateTime = (dateStr: string): string => {
  if (!dateStr) return ''
  
  // Match YYYY-MM-DD pattern (with optional time)
  const match = dateStr.match(/(\d{4})-(\d{2})-(\d{2})(.*)/)
  if (match) {
    const [, year, month, day, rest] = match
    return `${month}-${day}-${year}${rest}`
  }
  return dateStr
}

// Format all dates in a trip summary line from YYYY-MM-DD to MM-DD-YYYY
const formatTripSummaryItem = (item: string): string => {
  // Replace all YYYY-MM-DD patterns (with optional time) to MM-DD-YYYY
  return item.replace(/(\d{4})-(\d{2})-(\d{2})(\s+\d{2}:\d{2})?/g, (match, year, month, day, time) => {
    return `${month}-${day}-${year}${time || ''}`
  })
}

const parseFlightLine = (line: string, obj: Record<string, string>) => {
  const cleaned = line.replace(/^-\s*/, '').replace(/\*\*/g, '').trim()
  
  if (cleaned.includes('Airline:')) obj.airline = extractAfterFirstColon(cleaned)
  else if (cleaned.includes('Price:')) obj.price = extractAfterFirstColon(cleaned)
  else if (cleaned.includes('Departure:')) obj.departure = extractAfterFirstColon(cleaned)
  else if (cleaned.includes('Arrival:')) obj.arrival = extractAfterFirstColon(cleaned)
  else if (cleaned.includes('Stops:')) obj.stops = extractAfterFirstColon(cleaned)
  else if (cleaned.includes('→') || cleaned.includes('->')) {
    obj.route = cleaned.replace(/[🛫🛬✈️]/g, '').trim()
  }
}

const parseHotelLine = (line: string, obj: Record<string, string>) => {
  const cleaned = line.replace(/^-\s*/, '').replace(/\*\*/g, '').trim()
  
  if (cleaned.includes('Name:')) obj.name = extractAfterFirstColon(cleaned)
  else if (cleaned.includes('Price:')) obj.price = extractAfterFirstColon(cleaned)
  else if (cleaned.includes('Overall Rating:')) obj.rating = extractAfterFirstColon(cleaned).replace(/[⭐]/g, '').trim()
  else if (cleaned.includes('Location Rating:')) obj.locationRating = extractAfterFirstColon(cleaned)
  else if (cleaned.includes('Check-in:')) obj.checkIn = extractAfterFirstColon(cleaned)
}

const TravelResponseCard: React.FC<TravelResponseCardProps> = ({ content }) => {
  // Check if this looks like a structured travel response
  const isStructuredResponse = content.includes('Flight') && (content.includes('Hotel') || content.includes('$'))
  
  if (!isStructuredResponse) {
    // Render as simple markdown for non-travel responses
    return <SimpleMarkdown content={content} />
  }

  const sections = parseResponse(content)

  return (
    <div className="space-y-4">
      {/* Success Header */}
      {sections.intro && (
        <div className="flex items-center gap-3 rounded-xl bg-gradient-to-r from-[#3ce98a]/20 to-[#5feb9b]/10 p-4 border border-[#3ce98a]/30">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#3ce98a]">
            <span className="text-xl">🎉</span>
          </div>
          <div>
            <p className="font-semibold text-white">{sections.intro}</p>
            {sections.totalCost && (
              <p className="text-sm text-[#5feb9b]">Total trip cost: <span className="font-bold text-white">{sections.totalCost}</span></p>
            )}
          </div>
        </div>
      )}

      {/* Cost Breakdown */}
      {(sections.flightCost || sections.hotelCost) && (
        <div className="grid grid-cols-2 gap-3">
          {sections.flightCost && (
            <div className="flex items-center gap-3 rounded-lg bg-[#2a2a2a] p-3 border border-gray-700">
              <Plane className="h-5 w-5 text-[#5feb9b]" />
              <div>
                <p className="text-xs text-gray-400">Flights</p>
                <p className="font-semibold text-white">{sections.flightCost}</p>
              </div>
            </div>
          )}
          {sections.hotelCost && (
            <div className="flex items-center gap-3 rounded-lg bg-[#2a2a2a] p-3 border border-gray-700">
              <Hotel className="h-5 w-5 text-[#5feb9b]" />
              <div>
                <p className="text-xs text-gray-400">Hotel</p>
                <p className="font-semibold text-white">{sections.hotelCost}</p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Outbound Flight Card */}
      {sections.outboundFlight && Object.keys(sections.outboundFlight).length > 0 && (
        <FlightCard 
          title="Outbound Flight" 
          icon="🛫" 
          flight={sections.outboundFlight} 
        />
      )}

      {/* Return Flight Card */}
      {sections.returnFlight && Object.keys(sections.returnFlight).length > 0 && (
        <FlightCard 
          title="Return Flight" 
          icon="🛬" 
          flight={sections.returnFlight} 
        />
      )}

      {/* Hotel Card */}
      {sections.hotel && Object.keys(sections.hotel).length > 0 && (
        <HotelCard hotel={sections.hotel} />
      )}

      {/* Trip Summary */}
      {sections.tripSummary && sections.tripSummary.length > 0 && (
        <div className="rounded-xl bg-[#2a2a2a] border border-gray-700 overflow-hidden">
          <div className="flex items-center gap-2 bg-gradient-to-r from-[#3ce98a]/20 to-transparent px-4 py-3 border-b border-gray-700">
            <span className="text-lg">📋</span>
            <h3 className="font-semibold text-white">Trip Summary</h3>
          </div>
          <div className="p-4 space-y-2">
            {sections.tripSummary
              .filter(item => 
                !item.toLowerCase().includes('buffer to hotel') &&
                !item.toLowerCase().includes('outbound arrival')
              )
              .map((item, idx) => (
                <div key={idx} className="flex items-start gap-2 text-sm text-gray-300">
                  <span className="text-[#5feb9b] mt-0.5">•</span>
                  <span>{formatTripSummaryItem(item)}</span>
                </div>
              ))}
            {/* Add total cost if available */}
            {sections.totalCost && (
              <div className="flex items-start gap-2 text-sm text-gray-300 pt-2 mt-2 border-t border-gray-700">
                <span className="text-[#5feb9b] mt-0.5">💰</span>
                <span><strong className="text-white">Total Trip Cost:</strong> <span className="text-[#5feb9b] font-semibold">{sections.totalCost}</span></span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// Flight Card Component
const FlightCard: React.FC<{ title: string; icon: string; flight: Record<string, string> }> = ({ title, icon, flight }) => {
  const route = flight.route || ''
  const [from, to] = route.includes('→') ? route.split('→').map(s => s.trim()) : route.includes('->') ? route.split('->').map(s => s.trim()) : ['', '']

  return (
    <div className="rounded-xl bg-[#2a2a2a] border border-gray-700 overflow-hidden">
      <div className="flex items-center justify-between bg-gradient-to-r from-blue-500/20 to-transparent px-4 py-3 border-b border-gray-700">
        <div className="flex items-center gap-2">
          <span className="text-lg">{icon}</span>
          <h3 className="font-semibold text-white">{title}</h3>
        </div>
        {flight.price && (
          <span className="rounded-full bg-[#3ce98a]/20 px-3 py-1 text-sm font-semibold text-[#5feb9b]">
            {flight.price}
          </span>
        )}
      </div>
      
      <div className="p-4">
        {/* Route visualization */}
        {from && to && (
          <div className="flex items-center justify-between mb-4 px-2">
            <div className="text-center">
              <p className="text-2xl font-bold text-white">{from.replace(/[()]/g, '')}</p>
            </div>
            <div className="flex-1 flex items-center justify-center px-4">
              <div className="h-px flex-1 bg-gray-600"></div>
              <Plane className="h-5 w-5 text-[#5feb9b] mx-2 rotate-90" />
              <div className="h-px flex-1 bg-gray-600"></div>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-white">{to.replace(/[()]/g, '')}</p>
            </div>
          </div>
        )}

        {/* Flight details */}
        <div className="space-y-3 text-sm">
          {/* Airline and Stops row */}
          <div className="flex items-center justify-between">
            {flight.airline && (
              <div className="flex items-center gap-2">
                <span className="text-gray-500">Airline:</span>
                <span className="text-white font-medium">{flight.airline}</span>
              </div>
            )}
            {flight.stops && (
              <div className="flex items-center gap-2">
                <span className="text-gray-500">Stops:</span>
                <span className={`font-medium ${flight.stops.includes('Non-stop') || flight.stops.includes('0') ? 'text-[#5feb9b]' : 'text-yellow-400'}`}>
                  {flight.stops.includes('0') ? 'Non-stop' : flight.stops}
                </span>
              </div>
            )}
          </div>
          
          {/* Departure and Arrival times */}
          <div className="grid grid-cols-2 gap-4 pt-2 border-t border-gray-700">
            {flight.departure && (
              <div className="space-y-1">
                <div className="flex items-center gap-1.5 text-gray-500">
                  <Calendar className="h-3.5 w-3.5" />
                  <span className="text-xs uppercase tracking-wide">Departure</span>
                </div>
                <p className="text-white font-medium">{formatDateTime(flight.departure)}</p>
              </div>
            )}
            {flight.arrival && (
              <div className="space-y-1">
                <div className="flex items-center gap-1.5 text-gray-500">
                  <Clock className="h-3.5 w-3.5" />
                  <span className="text-xs uppercase tracking-wide">Arrival</span>
                </div>
                <p className="text-white font-medium">{formatDateTime(flight.arrival)}</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// Hotel Card Component
const HotelCard: React.FC<{ hotel: Record<string, string> }> = ({ hotel }) => {
  return (
    <div className="rounded-xl bg-[#2a2a2a] border border-gray-700 overflow-hidden">
      <div className="flex items-center justify-between bg-gradient-to-r from-purple-500/20 to-transparent px-4 py-3 border-b border-gray-700">
        <div className="flex items-center gap-2">
          <span className="text-lg">🏨</span>
          <h3 className="font-semibold text-white">Hotel</h3>
        </div>
        {hotel.price && (
          <span className="rounded-full bg-[#3ce98a]/20 px-3 py-1 text-sm font-semibold text-[#5feb9b]">
            {hotel.price}
          </span>
        )}
      </div>
      
      <div className="p-4">
        {hotel.name && (
          <h4 className="text-lg font-semibold text-white mb-3">{hotel.name}</h4>
        )}
        
        <div className="grid grid-cols-2 gap-3 text-sm">
          {hotel.rating && (
            <div className="flex items-center gap-2">
              <Star className="h-4 w-4 text-yellow-400 fill-yellow-400" />
              <span className="text-white">{hotel.rating}</span>
            </div>
          )}
          {hotel.locationRating && (
            <div className="flex items-center gap-2">
              <MapPin className="h-4 w-4 text-gray-500" />
              <span className="text-white">{hotel.locationRating}</span>
            </div>
          )}
          {hotel.checkIn && (
            <div className="flex items-center gap-2 col-span-2">
              <Clock className="h-4 w-4 text-gray-500" />
              <span className="text-gray-400">Check-in:</span>
              <span className="text-white">{hotel.checkIn}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// Simple markdown renderer for non-structured responses
const SimpleMarkdown: React.FC<{ content: string }> = ({ content }) => {
  // Convert markdown to styled elements
  const renderLine = (line: string, idx: number) => {
    let processed = line
    
    // Bold text **text**
    processed = processed.replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold text-white">$1</strong>')
    
    // Handle bullet points
    if (processed.trim().startsWith('- ')) {
      const bulletContent = processed.trim().substring(2)
      return (
        <div key={idx} className="flex items-start gap-2 text-gray-300">
          <span className="text-[#5feb9b] mt-1">•</span>
          <span dangerouslySetInnerHTML={{ __html: bulletContent }} />
        </div>
      )
    }
    
    // Separator
    if (processed.trim() === '---') {
      return <hr key={idx} className="border-gray-700 my-3" />
    }
    
    // Empty line
    if (!processed.trim()) {
      return <div key={idx} className="h-2" />
    }
    
    return (
      <p key={idx} className="text-gray-300" dangerouslySetInnerHTML={{ __html: processed }} />
    )
  }

  return (
    <div className="space-y-1">
      {content.split('\n').map((line, idx) => renderLine(line, idx))}
    </div>
  )
}

export default TravelResponseCard

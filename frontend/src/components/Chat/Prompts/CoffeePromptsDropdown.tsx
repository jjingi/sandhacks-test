/**
 * Copyright AGNTCY Contributors (https://github.com/agntcy)
 * SPDX-License-Identifier: Apache-2.0
 * 
 * Travel Prompts Dropdown Component
 * 
 * This component displays suggested travel search prompts to help users
 * understand what the travel agent can do. It fetches prompts from the
 * travel supervisor's /suggested-prompts endpoint.
 **/

import React, { useState, useRef, useEffect } from "react"
import LoadingSpinner from "./LoadingSpinner"
import InfoButton from "@/components/Chat/Prompts/InfoButton.tsx"
import { PromptCategory } from "./PromptTypes"

// API URL for the travel supervisor
const DEFAULT_TRAVEL_API_URL = "http://127.0.0.1:8000"
const TRAVEL_API_URL =
    import.meta.env.VITE_EXCHANGE_APP_API_URL || DEFAULT_TRAVEL_API_URL

interface TravelPromptsDropdownProps {
  visible: boolean
  onSelect: (query: string) => void
  pattern?: string
}


const TravelPromptsDropdown: React.FC<TravelPromptsDropdownProps> = ({
                                                                       visible,
                                                                       onSelect,
                                                                       pattern,
                                                                     }) => {
  const [isOpen, setIsOpen] = useState(false)
  const [categories, setCategories] = useState<PromptCategory[]>([])
  const dropdownRef = useRef<HTMLDivElement>(null)
  const [isLoading, setIsLoading] = useState(true)

  // Fetch travel prompts on mount or pattern change
  useEffect(() => {
    const controller = new AbortController()
    let retryTimeoutId: NodeJS.Timeout | null = null
    const MAX_RETRY_DELAY = 5000 // 5 seconds max

    const fetchPrompts = async (retryCount = 0) => {
      try {
        setIsLoading(true)
        // Check if using streaming pattern
        const isStreamingPattern = pattern === "travel_search_streaming"
        const url = isStreamingPattern
            ? `${TRAVEL_API_URL}/suggested-prompts?pattern=streaming`
            : `${TRAVEL_API_URL}/suggested-prompts`

        const res = await fetch(url, {
          cache: "no-cache",
          signal: controller.signal,
        })

        if (!res.ok) throw new Error(`HTTP ${res.status}`)

        const data: unknown = await res.json()

        console.log("Fetched travel prompts:", data)

        // Parse prompts from API response
        // Travel API returns: { travel: [...] } or { streaming: [...] }
        const categories = Object.entries(data).map(([key, value]) => ({
          name: key,
          // Handle both string arrays and object arrays
          prompts: Array.isArray(value) 
            ? value.map(item => typeof item === 'string' ? { prompt: item } : item)
            : [],
        }));
        setCategories(categories)

        // Retry if all categories are empty
        if (categories.every((category) => category.prompts.length === 0)) {
          const delay = Math.min(5000 * Math.pow(2, retryCount), MAX_RETRY_DELAY)
          retryTimeoutId = setTimeout(() => fetchPrompts(retryCount + 1), delay)
        }

        setIsLoading(false)
      } catch (err: unknown) {
        if (err instanceof Error && err.name !== "AbortError") {
          console.warn("Failed to load travel prompts from API.", err)
          // Retry on error with exponential backoff
          const delay = Math.min(5000 * Math.pow(2, retryCount), MAX_RETRY_DELAY)
          retryTimeoutId = setTimeout(() => fetchPrompts(retryCount + 1), delay)
        }
      }
    }

    fetchPrompts()

    return () => {
      controller.abort()
      if (retryTimeoutId) clearTimeout(retryTimeoutId)
    }
  }, [pattern])

  // Handle outside clicks and escape key
  useEffect(() => {
    if (!visible || !isOpen) return

    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }

    const handleEscapeKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsOpen(false)
      }
    }

    document.addEventListener("mousedown", handleClickOutside, true)
    document.addEventListener("keydown", handleEscapeKey)

    return () => {
      document.removeEventListener("mousedown", handleClickOutside, true)
      document.removeEventListener("keydown", handleEscapeKey)
    }
  }, [visible, isOpen])

  const handleToggle = () => setIsOpen(!isOpen)

  const handleItemClick = (item: string) => {
    onSelect(item)
    setIsOpen(false)
  }

  if (!visible) return null

  const dropdownClasses = `flex h-9 w-166 cursor-pointer flex-row items-center gap-1 rounded-lg bg-chat-background p-2 transition-colors duration-200 ease-in-out hover:bg-chat-background-hover ${
      isOpen ? "bg-chat-background-hover" : ""
  }`

  const hasNoPrompts = categories.every((category) => category.prompts.length === 0)

  const menuClasses = `absolute bottom-full left-0 z-[1000] mb-1 max-h-[365px] min-h-[50px] w-[320px] overflow-y-auto rounded-[6px] border border-nav-border bg-chat-dropdown-background px-[2px] py-0 opacity-100 shadow-[0px_2px_5px_0px_rgba(0,0,0,0.05)] ${
      isOpen ? "block animate-fadeInDropdown" : "hidden"
  }`;

  const iconClasses = `absolute bottom-[36.35%] left-[26.77%] right-[26.77%] top-[36.35%] bg-chat-dropdown-icon transition-transform duration-300 ease-in-out ${
      isOpen ? "rotate-180" : ""
  }`

  return (
      <div className="flex items-center gap-3">
        <div className="relative inline-block" ref={dropdownRef}>
          <div className={dropdownClasses} onClick={handleToggle}>
            <div className="order-0 flex h-5 w-122 flex-none flex-grow-0 flex-col items-start gap-1 p-0">
              <div className="order-0 h-5 w-122 flex-none flex-grow-0 self-stretch whitespace-nowrap font-cisco text-sm font-normal leading-5 text-chat-text">
                ✈️ Travel Prompts
              </div>
            </div>
            <div className="relative order-1 h-6 w-6 flex-none flex-grow-0">
              <div
                  className={iconClasses}
                  style={{ clipPath: "polygon(50% 100%, 0% 0%, 100% 0%)" }}
              />
            </div>
          </div>

          <div className={menuClasses}>
            {isLoading || hasNoPrompts ? (
                <LoadingSpinner message="Loading travel prompts, waiting for server response" />
            ) : (
                categories.map((category, index) => (
                    <div key={`category-${index}`} className="px-2 py-2">
                      {/* Category header for travel prompts */}
                      {category.name === "travel" && (
                          <div className="mb-2 h-[36px] w-full gap-2 bg-chat-dropdown-background pb-2 pl-[10px] pr-[10px] pt-2 font-cisco text-sm font-normal leading-5 tracking-[0%] text-chat-text opacity-60">
                            🔍 SEARCH TRIPS
                          </div>
                      )}
                      {category.name === "streaming" && (
                          <div className="mb-2 h-[36px] w-full gap-2 bg-chat-dropdown-background pb-2 pl-[10px] pr-[10px] pt-2 font-cisco text-sm font-normal leading-5 tracking-[0%] text-chat-text opacity-60">
                            ⚡ STREAMING SEARCH
                          </div>
                      )}
                      {category.prompts.map((item, idx) => (
                          <div
                              key={`prompt-${index}-${idx}`}
                              className={`flex mx-0.5 my-0.5 flex-col min-h-10 w-[calc(100%-4px)] cursor-pointer items-center bg-chat-dropdown-background px-2 py-[6px] transition-colors duration-200 ease-in-out hover:bg-chat-background-hover gap-y-1.5 border-t border-gray-400 border-opacity-40`}
                              onClick={() => handleItemClick(item.prompt)}
                          >
                            <div className="w-full break-words font-cisco text-sm font-normal leading-5 tracking-[0%] text-chat-text">
                              {item.prompt}
                            </div>
                            {item.description && (
                                <div className="w-full break-words font-cisco text-xs font-normal leading-4 tracking-[0%] text-chat-text opacity-70">
                                  {item.description}
                                </div>
                            )}
                          </div>
                      ))}
                    </div>
                ))
            )}
          </div>
        </div>
      </div>
  )
}

// Export as both TravelPromptsDropdown and the legacy name for compatibility
export default TravelPromptsDropdown
export { TravelPromptsDropdown as CoffeePromptsDropdown }
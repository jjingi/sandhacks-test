/**
 * Copyright AGNTCY Contributors (https://github.com/agntcy)
 * SPDX-License-Identifier: Apache-2.0
 * 
 * Travel Planning Agent Frontend Application
 * 
 * This is the main React application that provides a UI for interacting with
 * the Travel Planning Agent. It supports searching for flights and hotels.
 **/

import React, { useState, useEffect, useRef, useCallback } from "react"
import { LOCAL_STORAGE_KEY } from "@/components/Chat/Messages"
import { logger } from "@/utils/logger"
import { useChatAreaMeasurement } from "@/hooks/useChatAreaMeasurement"
import Navigation from "@/components/Navigation/Navigation"
import MainArea from "@/components/MainArea/MainArea"
import { useAgentAPI } from "@/hooks/useAgentAPI"
import ChatArea from "@/components/Chat/ChatArea"
import Sidebar from "@/components/Sidebar/Sidebar"
import { ThemeProvider } from "@/contexts/ThemeContext"
import { Message } from "./types/message"
import { getGraphConfig } from "@/utils/graphConfigs"
import { PATTERNS, PatternType } from "@/utils/patternUtils"
import TravelResponseCard from "@/components/Chat/TravelResponseCard"

interface ApiResponse {
  response: string
  session_id?: string
}

export interface ChatHistoryItem {
  id: string
  title: string
  timestamp: Date
  messages: Array<{
    role: 'user' | 'assistant'
    content: string
  }>
}

const CHAT_HISTORY_KEY = "travel_chat_history"

const App: React.FC = () => {
  const { sendMessage } = useAgentAPI()

  const [selectedPattern, setSelectedPattern] = useState<PatternType>(
    PATTERNS.TRAVEL_SEARCH,
  )

  const [aiReplied, setAiReplied] = useState<boolean>(false)
  const [buttonClicked, setButtonClicked] = useState<boolean>(false)
  const [currentUserMessage, setCurrentUserMessage] = useState<string>("")
  const [agentResponse, setAgentResponse] = useState<ApiResponse | undefined>(undefined)
  const [isAgentLoading, setIsAgentLoading] = useState<boolean>(false)
  const [apiError, setApiError] = useState<boolean>(false)
  const [showFinalResponse, setShowFinalResponse] = useState<boolean>(false)
  
  // Chat history state
  const [currentChatId, setCurrentChatId] = useState<string | null>(null)
  const [chatHistory, setChatHistory] = useState<ChatHistoryItem[]>([])
  const [conversationMessages, setConversationMessages] = useState<Array<{role: 'user' | 'assistant', content: string}>>([])

  // Load chat history from localStorage on mount
  useEffect(() => {
    const savedHistory = localStorage.getItem(CHAT_HISTORY_KEY)
    if (savedHistory) {
      try {
        const parsed = JSON.parse(savedHistory)
        setChatHistory(parsed.map((h: any) => ({
          ...h,
          timestamp: new Date(h.timestamp)
        })))
      } catch (e) {
        console.error("Error loading chat history:", e)
      }
    }
  }, [])

  // Save chat history to localStorage whenever it changes
  useEffect(() => {
    if (chatHistory.length > 0) {
      localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(chatHistory))
    }
  }, [chatHistory])

  const handlePatternChange = useCallback(
    (pattern: PatternType) => {
      setShowFinalResponse(false)
      setAgentResponse(undefined)
      setIsAgentLoading(false)
      setApiError(false)
      setCurrentUserMessage("")
      setButtonClicked(false)
      setAiReplied(false)
      setSelectedPattern(pattern)
    },
    [],
  )

  const [messages, setMessages] = useState<Message[]>(() => {
    const saved = localStorage.getItem(LOCAL_STORAGE_KEY)
    return saved ? JSON.parse(saved) : []
  })

  useEffect(() => {
    localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(messages))
  }, [messages])

  useEffect(() => {
    setButtonClicked(false)
    setAiReplied(false)
  }, [selectedPattern])

  const {
    height: chatHeight,
    isExpanded,
    chatRef,
  } = useChatAreaMeasurement({
    debounceMs: 100,
  })

  const chatHeightValue = currentUserMessage || agentResponse ? chatHeight : 76

  const handleUserInput = async (query: string) => {
    setCurrentUserMessage(query)
    setIsAgentLoading(true)
    setButtonClicked(true)
    setAiReplied(false) // Reset so animation plays
    setApiError(false)
    setShowFinalResponse(true)

    // Add user message to conversation
    const userMessage = { role: 'user' as const, content: query }
    const newMessages = [...conversationMessages, userMessage]
    setConversationMessages(newMessages)

    // Actually send the message to the API
    try {
      const response = await sendMessage(query, selectedPattern)
      handleApiResponse(response, false, query, newMessages)
    } catch (error) {
      logger.apiError("/agent/prompt", error)
      const errMessage = error instanceof Error ? error.message : String(error)
      handleApiResponse(errMessage, true, query, newMessages)
    }
  }

  // Accepts ApiResponse or string (for error fallback), but always sets ApiResponse
  const handleApiResponse = useCallback(
    (response: ApiResponse | string, isError: boolean = false, userQuery?: string, currentMessages?: Array<{role: 'user' | 'assistant', content: string}>) => {
      let apiResp: ApiResponse
      if (typeof response === "string") {
        apiResp = { response }
      } else {
        apiResp = response
      }
      setAgentResponse(apiResp)
      setIsAgentLoading(false)
      setAiReplied(true) // Mark as replied to stop animation
      setApiError(isError)

      // Add assistant response to conversation
      const assistantMessage = { role: 'assistant' as const, content: apiResp.response }
      const messagesToUse = currentMessages || conversationMessages
      const updatedMessages = [...messagesToUse, assistantMessage]
      setConversationMessages(updatedMessages)

      // Update or create chat history
      const queryToUse = userQuery || currentUserMessage
      if (queryToUse) {
        if (currentChatId) {
          // Update existing chat
          setChatHistory(prev => prev.map(chat => 
            chat.id === currentChatId 
              ? { ...chat, messages: updatedMessages, timestamp: new Date() }
              : chat
          ))
        } else {
          // Create new chat
          const title = queryToUse.length > 35 
            ? queryToUse.substring(0, 35) + "..." 
            : queryToUse
          
          const newChat: ChatHistoryItem = {
            id: `chat_${Date.now()}`,
            title: title,
            timestamp: new Date(),
            messages: updatedMessages
          }
          
          setChatHistory(prev => [newChat, ...prev].slice(0, 15))
          setCurrentChatId(newChat.id)
        }
      }

      setMessages((prev) => {
        const updated = [...prev]
        if (updated.length > 0) {
          updated[updated.length - 1] = {
            ...updated[updated.length - 1],
            content: apiResp.response,
            animate: !isError,
          }
        }
        return updated
      })
    },
    [setMessages, currentChatId, conversationMessages, currentUserMessage],
  )

  const handleDropdownSelect = async (query: string) => {
    setCurrentUserMessage(query)
    setIsAgentLoading(true)
    setButtonClicked(true)
    setAiReplied(false) // Reset so animation plays
    setApiError(false)
    setShowFinalResponse(true)

    // Add user message to conversation
    const userMessage = { role: 'user' as const, content: query }
    const newMessages = [...conversationMessages, userMessage]
    setConversationMessages(newMessages)

    try {
      const response = await sendMessage(query, selectedPattern)
      handleApiResponse(response, false, query, newMessages)
    } catch (error) {
      logger.apiError("/agent/prompt", error)
      const errMessage = error instanceof Error ? error.message : String(error)
      handleApiResponse(errMessage, true, query, newMessages)
    }
  }

  const handleClearConversation = () => {
    setMessages([])
    setCurrentUserMessage("")
    setAgentResponse(undefined)
    setIsAgentLoading(false)
    setButtonClicked(false)
    setAiReplied(false)
    setShowFinalResponse(false)
    setCurrentChatId(null)
    setConversationMessages([])
  }

  useEffect(() => {
    setCurrentUserMessage("")
    setAgentResponse(undefined)
    setIsAgentLoading(false)
    setButtonClicked(false)
    setAiReplied(false)
    setShowFinalResponse(false)
  }, [selectedPattern])

  const handleNewChat = () => {
    handleClearConversation()
  }

  // Handle selecting a chat from history
  const handleSelectChat = (chatId: string) => {
    const selectedChat = chatHistory.find(chat => chat.id === chatId)
    if (selectedChat && selectedChat.messages.length > 0) {
      setCurrentChatId(chatId)
      setConversationMessages(selectedChat.messages)
      
      // Find the last user message and last assistant response
      const lastUserMsg = [...selectedChat.messages].reverse().find(m => m.role === 'user')
      const lastAssistantMsg = [...selectedChat.messages].reverse().find(m => m.role === 'assistant')
      
      if (lastUserMsg) {
        setCurrentUserMessage(lastUserMsg.content)
      }
      if (lastAssistantMsg) {
        setAgentResponse({ response: lastAssistantMsg.content })
        setShowFinalResponse(true)
      }
      setButtonClicked(false)
      setAiReplied(true)
    }
  }

  // Handle deleting a chat
  const handleDeleteChat = (chatId: string) => {
    setChatHistory(prev => prev.filter(chat => chat.id !== chatId))
    if (currentChatId === chatId) {
      handleClearConversation()
    }
  }

  // Determine if we should show the graph
  // Show graph when: no messages (new chat), or when loading (animation)
  const showGraph = conversationMessages.length === 0 || isAgentLoading
  
  // Show welcome section only when it's a fresh new chat (no messages)
  const showWelcome = conversationMessages.length === 0

  return (
    <ThemeProvider>
      <div className="flex h-screen w-screen flex-col overflow-hidden bg-[#212121]">
        <Navigation />
        <div className="flex flex-1 overflow-hidden">
          <Sidebar
            selectedPattern={selectedPattern}
            onPatternChange={handlePatternChange}
            onNewChat={handleNewChat}
            onSelectChat={handleSelectChat}
            onDeleteChat={handleDeleteChat}
            chatHistory={chatHistory}
            currentChatId={currentChatId}
          />
          <div className="flex flex-1 flex-col border-l border-gray-800 bg-[#212121]">
            {/* Main content area - scrollable */}
            <div className="relative flex-1 overflow-y-auto">
              {/* New Chat Welcome View - Graph + Welcome Section */}
              {showWelcome && (
                <div className="flex h-full flex-col">
                  {/* Agent Graph - takes up available space above welcome */}
                  <div className="flex-1 min-h-[300px]">
                    <MainArea
                      pattern={selectedPattern}
                      buttonClicked={buttonClicked}
                      setButtonClicked={setButtonClicked}
                      aiReplied={aiReplied}
                      setAiReplied={setAiReplied}
                      chatHeight={chatHeightValue}
                      isExpanded={isExpanded}
                      groupCommResponseReceived={false}
                      onNodeHighlight={() => {}}
                    />
                  </div>
                  
                  {/* Welcome Section */}
                  <div className="flex flex-col items-center justify-center px-4 pb-4">
                    {/* Airplane Icon - tilted for dynamic look */}
                    <div className="mb-4">
                      <svg 
                        className="h-12 w-12 text-[#3ce98a] -rotate-45" 
                        viewBox="0 0 24 24" 
                        fill="none" 
                        stroke="currentColor" 
                        strokeWidth="2"
                      >
                        <path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" />
                      </svg>
                    </div>
                    
                    {/* Welcome Text */}
                    <h1 className="mb-2 text-2xl font-semibold text-white">
                      How can I help you plan your trip?
                    </h1>
                    <p className="text-gray-400">
                      Find flights, hotels, and activities for your next adventure
                    </p>
                  </div>
                </div>
              )}
              
              {/* Loading State with Graph - when messages exist but loading */}
              {!showWelcome && isAgentLoading && (
                <div className="h-[350px]">
                  <MainArea
                    pattern={selectedPattern}
                    buttonClicked={buttonClicked}
                    setButtonClicked={setButtonClicked}
                    aiReplied={aiReplied}
                    setAiReplied={setAiReplied}
                    chatHeight={chatHeightValue}
                    isExpanded={isExpanded}
                    groupCommResponseReceived={false}
                    onNodeHighlight={() => {}}
                  />
                </div>
              )}

              {/* Conversation Messages - shown when there are messages */}
              {conversationMessages.length > 0 && (
                <div className="flex flex-col items-center px-4 py-6 sm:px-8 md:px-16 lg:px-[120px]">
                  <div className="w-full max-w-[800px] space-y-6">
                    {/* Render all conversation messages */}
                    {conversationMessages.map((msg, index) => (
                      <div key={index} className="flex items-start gap-3">
                        {msg.role === 'user' ? (
                          <>
                            <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-gray-600">
                              <svg className="h-4 w-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                              </svg>
                            </div>
                            <div className="flex-1 text-sm text-gray-100">{msg.content}</div>
                          </>
                        ) : (
                          <>
                            <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full" style={{background: 'linear-gradient(135deg, #3ce98a, #5feb9b)'}}>
                              <svg className="h-4 w-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                              </svg>
                            </div>
                            <div className="flex-1 text-sm">
                              <TravelResponseCard content={msg.content} />
                            </div>
                          </>
                        )}
                      </div>
                    ))}

                    {/* Loading indicator for new response */}
                    {isAgentLoading && (
                      <div className="flex items-start gap-3">
                        <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full" style={{background: 'linear-gradient(135deg, #3ce98a, #5feb9b)'}}>
                          <svg className="h-4 w-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                          </svg>
                        </div>
                        <div className="flex-1 text-sm text-gray-200">
                          <div className="flex items-center gap-2 text-[#5feb9b]">
                            <div className="h-2 w-2 animate-bounce rounded-full bg-[#3ce98a] [animation-delay:-0.3s]"></div>
                            <div className="h-2 w-2 animate-bounce rounded-full bg-[#5feb9b] [animation-delay:-0.15s]"></div>
                            <div className="h-2 w-2 animate-bounce rounded-full bg-[#7becac]"></div>
                            <span className="ml-2">Searching for the best deals...</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
            
            {/* Input area - fixed at bottom */}
            <div className="flex w-full flex-none flex-col items-center justify-end gap-0 bg-[#212121] px-4 pb-6 pt-2">
              <ChatArea
                setMessages={setMessages}
                setButtonClicked={setButtonClicked}
                setAiReplied={setAiReplied}
                isBottomLayout={true}
                showCoffeePrompts={false}
                showLogisticsPrompts={false}
                showProgressTracker={false}
                showAuctionStreaming={false}
                showFinalResponse={showFinalResponse}
                onStreamComplete={() => {}}
                onSenderHighlight={() => {}}
                pattern={selectedPattern}
                graphConfig={getGraphConfig(selectedPattern, false)}
                onDropdownSelect={handleDropdownSelect}
                onUserInput={handleUserInput}
                onApiResponse={handleApiResponse}
                onClearConversation={handleClearConversation}
                currentUserMessage={currentUserMessage}
                agentResponse={agentResponse}
                executionKey=""
                isAgentLoading={isAgentLoading}
                apiError={apiError}
                chatRef={chatRef}
                auctionState={{
                  events: [],
                  status: "idle",
                  error: null,
                }}
              />
            </div>
          </div>
        </div>
      </div>
    </ThemeProvider>
  )
}

export default App

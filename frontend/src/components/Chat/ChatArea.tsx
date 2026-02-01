/**
 * Copyright AGNTCY Contributors (https://github.com/agntcy)
 * SPDX-License-Identifier: Apache-2.0
 **/

import React, { useState } from "react"
import { Message } from "@/types/message"
import { Plane, Send } from "lucide-react"
import CoffeePromptsDropdown from "./Prompts/CoffeePromptsDropdown"
import LogisticsPromptsDropdown from "./Prompts/LogisticsPromptsDropdown"
import { useAgentAPI } from "@/hooks/useAgentAPI"
import UserMessage from "./UserMessage"
import ChatHeader from "./ChatHeader"
import TravelAgentIcon from "@/assets/Travel_Icon.svg"
import { useGroupSessionId } from "@/stores/groupStreamingStore"

import grafanaIcon from "@/assets/grafana.svg"
import ExternalLinkButton from "./ExternalLinkButton"

import { cn } from "@/utils/cn.ts"
import { logger } from "@/utils/logger"
import GroupCommunicationFeed from "./GroupCommunicationFeed"
import AuctionStreamingFeed from "./AuctionStreamingFeed"
import axios from "axios";

const DEFAULT_GRAFANA_URL = "http://127.0.0.1:3001"
const GRAFANA_URL =
    import.meta.env.VITE_GRAFANA_URL || DEFAULT_GRAFANA_URL
const GRAFANA_DASHBOARD_PATH = "/d/lungo-dashboard/lungo-dashboard?orgId=1&var-session_id="

interface ApiResponse {
    response: string
    session_id?: string
}

interface ChatAreaProps {
    setMessages: React.Dispatch<React.SetStateAction<Message[]>>
    setButtonClicked: (clicked: boolean) => void
    setAiReplied: (replied: boolean) => void
    isBottomLayout: boolean
    showCoffeePrompts?: boolean
    showLogisticsPrompts?: boolean
    showProgressTracker?: boolean
    showAuctionStreaming?: boolean
    showFinalResponse?: boolean
    onStreamComplete?: () => void
    onSenderHighlight?: (nodeId: string) => void
    pattern?: string
    graphConfig?: any
    onDropdownSelect?: (query: string) => void
    onUserInput?: (query: string) => void
    onApiResponse?: (response: string, isError?: boolean) => void
    onClearConversation?: () => void
    currentUserMessage?: string
    agentResponse?: ApiResponse
    executionKey?: string
    isAgentLoading?: boolean
    apiError: boolean
    chatRef?: React.RefObject<HTMLDivElement | null>
    auctionState?: any
    grafanaUrl?: string // Add this prop if you want to pass the URL dynamically
}

const ChatArea: React.FC<ChatAreaProps> = ({
                                               setMessages,
                                               setButtonClicked,
                                               setAiReplied,
                                               isBottomLayout,
                                               showCoffeePrompts = false,
                                               showLogisticsPrompts = false,
                                               showProgressTracker = false,
                                               showAuctionStreaming = false,
                                               showFinalResponse = false,
                                               onStreamComplete,
                                               onSenderHighlight,
                                               pattern,
                                               graphConfig,
                                               onDropdownSelect,
                                               onUserInput,
                                               onApiResponse,
                                               onClearConversation,
                                               currentUserMessage,
                                               agentResponse,
                                               executionKey,
                                               isAgentLoading,
                                               apiError,
                                               chatRef,
                                               auctionState,
                                               grafanaUrl = GRAFANA_URL
                                           }) => {

    const [content, setContent] = useState<string>("")
    const [loading, setLoading] = useState<boolean>(false)
    const [isMinimized, setIsMinimized] = useState<boolean>(false)
    const { sendMessageWithCallback } = useAgentAPI()

    const handleMinimize = () => {
        setIsMinimized(true)
    }

    const handleRestore = () => {
        setIsMinimized(false)
    }

    const handleDropdownQuery = (query: string) => {
        if (isMinimized) {
            setIsMinimized(false)
        }

        if (onDropdownSelect) {
            onDropdownSelect(query)
        }
    }

    const processMessageWithQuery = async (
        messageContent: string,
    ): Promise<void> => {
        if (!messageContent.trim()) return

        setContent("")
        setLoading(true)
        setButtonClicked(true)

        await sendMessageWithCallback(
            messageContent,
            setMessages,
            {
                onSuccess: (response: ApiResponse) => {
                    setAiReplied(true)
                    if (onApiResponse) {
                        onApiResponse(response.response ?? "", false)
                    }
                },
                onError: (error) => {
                    logger.apiError("/agent/prompt", error)
                    let errorMessage = "Sorry, I encountered an error"
                    if (axios.isAxiosError(error) && error.response?.data?.detail) {
                        errorMessage = error.response.data.detail
                    }
                    if (onApiResponse) {
                        onApiResponse(errorMessage, true)
                    }
                },
            },
            pattern,
        );

        setLoading(false)
    }

    const processMessage = async (): Promise<void> => {
        if (!content.trim()) return
        
        if (isMinimized) {
            setIsMinimized(false)
        }

        // If onUserInput is provided (from App.tsx), use it and return
        // App.tsx handles the API call and response
        if (onUserInput) {
            const messageContent = content
            setContent("")
            onUserInput(messageContent)
            return
        }

        if ((showAuctionStreaming || showProgressTracker) && onDropdownSelect) {
            setContent("")
            onDropdownSelect(content)
        } else {
            await processMessageWithQuery(content)
        }
    }

    const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>): void => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault()
            processMessage()
        }
    }

    // Build the Grafana URL with session_id if available
    const groupSessionId = useGroupSessionId()
    const sessionIdForUrl = agentResponse?.session_id || groupSessionId

    const grafanaSessionUrl = sessionIdForUrl
        ? `${grafanaUrl}${GRAFANA_DASHBOARD_PATH}${encodeURIComponent(sessionIdForUrl)}`
        : grafanaUrl


    if (!isBottomLayout) {
        return null
    }

    return (
        <div
            ref={chatRef}
            className="relative flex w-full flex-col bg-[#212121]"
        >
            {/* Input area - always visible at bottom */}
            <div className="flex w-full flex-col items-center gap-3 px-4 py-4">
                {showCoffeePrompts && (
                    <div className="relative z-10 flex w-full max-w-[680px] justify-center">
                        <CoffeePromptsDropdown
                            visible={true}
                            onSelect={handleDropdownQuery}
                            pattern={pattern}
                        />
                    </div>
                )}

                <div className="flex w-full max-w-[680px] flex-col items-stretch gap-0 p-0">
                    <div className="relative box-border flex min-h-[52px] flex-1 flex-row items-center rounded-3xl border border-gray-700 bg-[#2f2f2f] px-4 py-2 transition-all focus-within:border-gray-600">
                        <div className="flex h-full w-full flex-row items-center gap-3">
                            <input
                                className="h-6 min-w-0 flex-1 border-none bg-transparent font-inter text-[15px] font-normal leading-5 text-gray-100 outline-none placeholder:text-gray-500"
                                placeholder="Ask anything"
                                value={content}
                                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                                    setContent(e.target.value)
                                }
                                onKeyPress={handleKeyPress}
                                disabled={loading || isAgentLoading}
                            />
                            <button
                                onClick={() => {
                                    if (content.trim() && !loading && !isAgentLoading) {
                                        processMessage()
                                    }
                                }}
                                disabled={!content.trim() || loading || isAgentLoading}
                                className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-full border-none transition-all disabled:cursor-not-allowed disabled:opacity-30"
                                style={{background: content.trim() ? 'linear-gradient(135deg, #3ce98a, #5feb9b)' : '#424242'}}
                            >
                                <Send className="h-4 w-4 text-white" />
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}

export default ChatArea
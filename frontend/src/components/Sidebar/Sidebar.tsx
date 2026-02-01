/**
 * Copyright AGNTCY Contributors (https://github.com/agntcy)
 * SPDX-License-Identifier: Apache-2.0
 **/

import React, { useState } from "react"
import { Plus, MessageSquare, Clock, Trash2, ChevronDown } from "lucide-react"
import {
  PatternType,
} from "@/utils/patternUtils"
import { ChatHistoryItem } from "@/App"

interface SidebarProps {
  selectedPattern: PatternType
  onPatternChange: (pattern: PatternType) => void
  onNewChat?: () => void
  onSelectChat?: (chatId: string) => void
  onDeleteChat?: (chatId: string) => void
  chatHistory: ChatHistoryItem[]
  currentChatId: string | null
}

const Sidebar: React.FC<SidebarProps> = ({
  selectedPattern,
  onPatternChange,
  onNewChat,
  onSelectChat,
  onDeleteChat,
  chatHistory,
  currentChatId,
}) => {
  const [isHistoryExpanded, setIsHistoryExpanded] = useState(true)

  const handleNewChat = () => {
    if (onNewChat) onNewChat()
  }

  const handleSelectChat = (chatId: string) => {
    if (onSelectChat) onSelectChat(chatId)
  }

  const handleDeleteChat = (e: React.MouseEvent, chatId: string) => {
    e.stopPropagation()
    if (onDeleteChat) onDeleteChat(chatId)
  }

  const formatTimestamp = (date: Date) => {
    const now = new Date()
    const dateObj = new Date(date)
    const diffMs = now.getTime() - dateObj.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 1) return "Just now"
    if (diffMins < 60) return `${diffMins}m ago`
    if (diffHours < 24) return `${diffHours}h ago`
    if (diffDays < 7) return `${diffDays}d ago`
    return dateObj.toLocaleDateString()
  }

  return (
    <div className="flex h-full w-64 flex-none flex-col border-r border-gray-800 bg-[#171717] font-inter lg:w-[260px]">
      {/* New Chat Button */}
      <div className="p-3">
        <button
          onClick={handleNewChat}
          className="group flex w-full items-center gap-3 rounded-lg border border-gray-700 bg-transparent px-3 py-2.5 transition-all hover:bg-gray-800"
        >
          <Plus className="h-4 w-4 text-gray-300" />
          <span className="flex-1 text-left text-sm font-medium text-gray-300">
            New chat
          </span>
        </button>
      </div>

      {/* Chat History Section */}
      <div className="flex flex-1 flex-col overflow-hidden px-2">
        <button
          onClick={() => setIsHistoryExpanded(!isHistoryExpanded)}
          className="mb-1 flex items-center gap-2 rounded-lg px-2 py-2 text-xs font-medium text-gray-500 transition-colors hover:text-gray-400"
        >
          <Clock className="h-3.5 w-3.5" />
          <span className="flex-1 text-left">Your searches</span>
          <ChevronDown className={`h-3.5 w-3.5 transition-transform ${isHistoryExpanded ? '' : '-rotate-90'}`} />
        </button>

        {isHistoryExpanded && (
          <div className="flex-1 space-y-0.5 overflow-y-auto scrollbar-thin scrollbar-track-transparent scrollbar-thumb-gray-700">
            {chatHistory.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-center">
                <MessageSquare className="mb-2 h-5 w-5 text-gray-600" />
                <p className="text-xs text-gray-500">No recent searches</p>
              </div>
            ) : (
              chatHistory.map((chat) => (
                <button
                  key={chat.id}
                  onClick={() => handleSelectChat(chat.id)}
                  className={`group flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left transition-all ${
                    currentChatId === chat.id
                      ? "bg-gray-800"
                      : "hover:bg-gray-800/50"
                  }`}
                >
                  <MessageSquare className="h-4 w-4 flex-shrink-0 text-gray-500" />
                  <div className="flex flex-1 flex-col min-w-0">
                    <span className="truncate text-sm text-gray-300">
                      {chat.title}
                    </span>
                    <span className="text-xs text-gray-500">
                      {formatTimestamp(chat.timestamp)}
                    </span>
                  </div>
                  <button
                    onClick={(e) => handleDeleteChat(e, chat.id)}
                    className="flex-shrink-0 rounded p-1 opacity-0 transition-opacity hover:bg-gray-700 group-hover:opacity-100"
                  >
                    <Trash2 className="h-3.5 w-3.5 text-gray-500 hover:text-red-400" />
                  </button>
                </button>
              ))
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="border-t border-gray-800 p-3">
        <div className="flex items-center gap-2 rounded-lg px-2 py-2" style={{background: 'linear-gradient(to right, #3ce98a20, #abedc920)'}}>
          <div className="h-2 w-2 animate-pulse rounded-full bg-[#3ce98a]" />
          <span className="text-xs text-[#5feb9b]">AI Travel Agent Ready</span>
        </div>
      </div>
    </div>
  )
}

export default Sidebar

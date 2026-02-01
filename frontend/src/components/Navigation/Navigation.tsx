/**
 * Copyright AGNTCY Contributors (https://github.com/agntcy)
 * SPDX-License-Identifier: Apache-2.0
 **/

import React, { useState } from "react"
import { HelpCircle, Plane } from "lucide-react"
import travelAgntcyLogo from "@/assets/travel_agntcy_logo.svg"
import ThemeToggleIcon from "../icons/ThemeToggleIcon"
import { useTheme } from "@/hooks/useTheme"
import InfoModal from "./InfoModal"

const Navigation: React.FC = () => {
  const [isModalOpen, setIsModalOpen] = useState(false)
  const { isLightMode, toggleTheme } = useTheme()

  const handleHelpClick = () => {
    setIsModalOpen(true)
  }

  const handleCloseModal = () => {
    setIsModalOpen(false)
  }

  const handleThemeToggle = () => {
    toggleTheme()
  }

  return (
    <div className="order-0 box-border flex h-[56px] w-full flex-none flex-grow-0 flex-col items-start self-stretch p-0">
      <div className="order-0 box-border flex h-[56px] w-full flex-none flex-grow-0 flex-row items-center justify-between gap-2 self-stretch border-b border-emerald-400/30 px-2 py-[10px] shadow-lg sm:px-4" style={{backgroundImage: 'linear-gradient(to right, #3ce98a, #5feb9b, #7becac, #94edbb, #abedc9)'}}>
        {/* Logo Section */}
        <div className="order-0 ml-2 flex h-[45px] flex-none flex-grow-0 flex-row items-center gap-3 p-0 sm:ml-4">
          {/* Animated Airplane Icon */}
          <div className="relative flex h-9 w-9 items-center justify-center rounded-lg bg-white/30 shadow-sm">
            <Plane className="h-5 w-5 text-gray-800" strokeWidth={2} />
          </div>
          
          {/* Brand Text */}
          <div className="flex flex-col">
            <span className="text-lg font-semibold tracking-tight text-gray-800">
              Travel AGNTCY
            </span>
          </div>
        </div>

        {/* Right Actions */}
        <div className="order-3 flex flex-none flex-grow-0 flex-row items-center justify-end gap-1 p-0">
          <button
            className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/20 p-2 transition-all hover:bg-white/30"
            title={`Switch to ${isLightMode ? "dark" : "light"} mode`}
            aria-label={`Switch to ${isLightMode ? "dark" : "light"} mode`}
            onClick={handleThemeToggle}
          >
            <ThemeToggleIcon className="h-4 w-4 text-gray-800" />
          </button>
          <button
            className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/20 p-2 transition-all hover:bg-white/30"
            title="Help"
            onClick={handleHelpClick}
          >
            <HelpCircle className="h-4 w-4 text-gray-800" />
          </button>
        </div>
      </div>

      <InfoModal isOpen={isModalOpen} onClose={handleCloseModal} />
    </div>
  )
}

export default Navigation

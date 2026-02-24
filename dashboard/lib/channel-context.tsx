"use client"

import { createContext, useContext, useState, useEffect } from "react"

export type ChannelName = "CAZETV" | "GETV"
export const CHANNELS: ChannelName[] = ["CAZETV", "GETV"]

type ChannelContextType = {
  selected: Record<ChannelName, boolean>
  toggle: (ch: ChannelName) => void
}

const ChannelContext = createContext<ChannelContextType>({
  selected: { CAZETV: true, GETV: true },
  toggle: () => {},
})

export function ChannelProvider({ children }: { children: React.ReactNode }) {
  const [selected, setSelected] = useState<Record<ChannelName, boolean>>({ CAZETV: true, GETV: true })

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("channel_selected") ?? "null")
      if (Array.isArray(saved)) {
        setSelected({ CAZETV: saved.includes("CAZETV"), GETV: saved.includes("GETV") })
      } else {
        const oldTab = localStorage.getItem("channel_tab")
        if (oldTab === "CAZETV") setSelected({ CAZETV: true, GETV: false })
        if (oldTab === "GETV")   setSelected({ CAZETV: false, GETV: true })
      }
    } catch {}
  }, [])

  const toggle = (ch: ChannelName) => {
    setSelected((prev) => {
      const next = { ...prev, [ch]: !prev[ch] }
      try {
        localStorage.setItem("channel_selected", JSON.stringify(CHANNELS.filter((k) => next[k])))
      } catch {}
      return next
    })
  }

  return <ChannelContext.Provider value={{ selected, toggle }}>{children}</ChannelContext.Provider>
}

export const useChannels = () => useContext(ChannelContext)

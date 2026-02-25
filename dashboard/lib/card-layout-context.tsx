"use client"

import { createContext, useContext, useState, useEffect, useCallback } from "react"

export type SortMode = "manual" | "cazetv-first" | "getv-first" | "split-lr"

interface CardLayoutState {
  sortMode: SortMode
  pinnedIds: string[]
  manualOrder: string[]
}

interface CardLayoutContextType extends CardLayoutState {
  setSortMode: (mode: SortMode) => void
  togglePin: (videoId: string) => void
  reorder: (fromId: string, toId: string) => void
}

const defaultState: CardLayoutState = {
  sortMode: "manual",
  pinnedIds: [],
  manualOrder: [],
}

const CardLayoutContext = createContext<CardLayoutContextType>({
  ...defaultState,
  setSortMode: () => {},
  togglePin: () => {},
  reorder: () => {},
})

export function CardLayoutProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<CardLayoutState>(defaultState)

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("card_layout") ?? "null")
      if (saved && typeof saved === "object") {
        setState((prev) => ({
          sortMode: saved.sortMode ?? prev.sortMode,
          pinnedIds: Array.isArray(saved.pinnedIds) ? saved.pinnedIds : prev.pinnedIds,
          manualOrder: Array.isArray(saved.manualOrder) ? saved.manualOrder : prev.manualOrder,
        }))
      }
    } catch {}
  }, [])

  const save = (next: CardLayoutState) => {
    try { localStorage.setItem("card_layout", JSON.stringify(next)) } catch {}
  }

  const setSortMode = useCallback((mode: SortMode) => {
    setState((prev) => {
      const next = { ...prev, sortMode: mode }
      save(next)
      return next
    })
  }, [])

  const togglePin = useCallback((videoId: string) => {
    setState((prev) => {
      const pinned = prev.pinnedIds.includes(videoId)
        ? prev.pinnedIds.filter((id) => id !== videoId)
        : [...prev.pinnedIds, videoId]
      const next = { ...prev, pinnedIds: pinned }
      save(next)
      return next
    })
  }, [])

  const reorder = useCallback((fromId: string, toId: string) => {
    setState((prev) => {
      const order = [...prev.manualOrder]
      const fromIdx = order.indexOf(fromId)
      const toIdx = order.indexOf(toId)
      if (fromIdx === -1 || toIdx === -1 || fromIdx === toIdx) return prev
      order.splice(fromIdx, 1)
      order.splice(toIdx, 0, fromId)
      const next = { ...prev, manualOrder: order, sortMode: "manual" as SortMode }
      save(next)
      return next
    })
  }, [])

  return (
    <CardLayoutContext.Provider value={{ ...state, setSortMode, togglePin, reorder }}>
      {children}
    </CardLayoutContext.Provider>
  )
}

export const useCardLayout = () => useContext(CardLayoutContext)

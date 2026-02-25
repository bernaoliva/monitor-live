"use client"

import { Pin } from "lucide-react"
import type { SortMode } from "@/lib/card-layout-context"

interface LayoutToolbarProps {
  sortMode: SortMode
  onSortChange: (mode: SortMode) => void
  pinnedCount: number
}

const MODES: { mode: SortMode; label: string }[] = [
  { mode: "cazetv-first", label: "CazeTV 1°" },
  { mode: "getv-first",   label: "GETV 1°"   },
  { mode: "split-lr",     label: "L / R"      },
  { mode: "manual",       label: "Manual"     },
]

export default function LayoutToolbar({ sortMode, onSortChange, pinnedCount }: LayoutToolbarProps) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="text-[9px] text-white/20 font-mono uppercase tracking-widest shrink-0">Ordem:</span>
      <div className="flex items-center gap-1">
        {MODES.map(({ mode, label }) => (
          <button
            key={mode}
            onClick={() => onSortChange(mode)}
            className={`px-2 py-1 rounded text-[9px] font-bold font-mono tracking-wide transition-all ${
              sortMode === mode
                ? "bg-white/15 text-white"
                : "bg-white/[0.04] text-white/30 hover:bg-white/[0.08] hover:text-white/55"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      {pinnedCount > 0 && (
        <div className="flex items-center gap-1 px-2 py-1 rounded bg-amber-500/10 border border-amber-500/20">
          <Pin size={8} className="text-amber-400/70" />
          <span className="text-[9px] font-bold font-mono text-amber-400/70">{pinnedCount} fixado{pinnedCount > 1 ? "s" : ""}</span>
        </div>
      )}
    </div>
  )
}

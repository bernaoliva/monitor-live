"use client"

import { useEffect, useRef, useState, useCallback } from "react"
import { collection, onSnapshot } from "firebase/firestore"
import { db } from "@/lib/firebase"
import { Live } from "@/lib/types"
import LiveCard from "@/components/LiveCard"
import LayoutToolbar from "@/components/LayoutToolbar"
import { Tv2, Wifi, WifiOff, Activity, Pin } from "lucide-react"
import { useChannels } from "@/lib/channel-context"
import type { ChannelName } from "@/lib/channel-context"
import { useCardLayout } from "@/lib/card-layout-context"
import type { SortMode } from "@/lib/card-layout-context"

const CHANNELS: ChannelName[] = ["CAZETV", "GETV"]

function gapFor(total: number): string {
  return total >= 7 ? "gap-2" : total >= 4 ? "gap-3" : "gap-4"
}

function gridClass(n: number): string {
  if (n <= 1) return ""
  const gap = gapFor(n)
  if (n === 2) return `grid grid-cols-2 ${gap}`
  if (n === 3) return `grid grid-cols-3 ${gap}`
  if (n === 4) return `grid grid-cols-2 ${gap}`
  if (n <= 6)  return `grid grid-cols-3 ${gap}`
  if (n <= 8)  return `grid grid-cols-4 ${gap}`
  return `grid grid-cols-5 ${gap}`
}

// Grid dos fixados: cols baseado em pinned.length (max 5), gap baseado no TOTAL
function pinnedGridClass(pinnedCount: number, totalCount: number): string {
  if (pinnedCount <= 1) return ""
  const gap  = gapFor(totalCount)
  const cols = Math.min(pinnedCount, 5)
  return `grid grid-cols-${cols} ${gap}`
}

// Divide os não-fixados em [linhas completas de 5, sobras da última linha]
function splitUnpinned<T>(items: T[]): [T[], T[]] {
  const full = Math.floor(items.length / 5) * 5
  return [items.slice(0, full), items.slice(full)]
}

function innerGridClass(n: number): string {
  if (n <= 1) return ""
  if (n === 2) return "grid grid-cols-2 gap-3"
  return "grid grid-cols-2 gap-2"
}

function sortLives(lives: Live[], mode: SortMode, manualOrder: string[]): Live[] {
  if (mode === "manual") {
    return [...lives].sort((a, b) => {
      const ia = manualOrder.indexOf(a.video_id)
      const ib = manualOrder.indexOf(b.video_id)
      return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib)
    })
  }
  if (mode === "cazetv-first") {
    return [...lives].sort((a) => (a.channel.toUpperCase() === "CAZETV" ? -1 : 1))
  }
  if (mode === "getv-first") {
    return [...lives].sort((a) => (a.channel.toUpperCase() === "GETV" ? -1 : 1))
  }
  return lives
}

export default function HomePage() {
  const [lives, setLives]         = useState<Live[]>([])
  const [connected, setConnected] = useState(false)
  const [hidden, setHidden]       = useState<Set<string>>(new Set())
  const { selected: selectedChannels } = useChannels()
  const { sortMode, pinnedIds, manualOrder, setSortMode, togglePin, reorder } = useCardLayout()
  const orderRef = useRef<string[]>([])

  const [draggingId, setDraggingId] = useState<string | null>(null)
  const [dragOverId, setDragOverId] = useState<string | null>(null)

  // Carrega IDs ocultos do localStorage apenas no cliente
  useEffect(() => {
    try {
      setHidden(new Set(JSON.parse(localStorage.getItem("hidden_lives") ?? "[]")))
    } catch {}
  }, [])

  const hideCard = (videoId: string) => {
    setHidden((prev) => {
      const next = new Set([...prev, videoId])
      try { localStorage.setItem("hidden_lives", JSON.stringify([...next])) } catch {}
      return next
    })
  }

  useEffect(() => {
    const unsub = onSnapshot(
      collection(db, "lives"),
      (snap) => {
        setConnected(true)
        const data = snap.docs.map((doc) => {
          const d = doc.data()
          return {
            video_id:           doc.id,
            channel:            d.channel            ?? "",
            title:              d.title              ?? doc.id,
            url:                d.url                ?? "",
            status:             d.status             ?? "ended",
            started_at:         d.started_at         ?? "",
            ended_at:           d.ended_at           ?? null,
            last_seen_at:       d.last_seen_at       ?? "",
            total_comments:     d.total_comments     ?? 0,
            technical_comments: d.technical_comments ?? 0,
            issue_counts:       d.issue_counts       ?? {},
            concurrent_viewers: d.concurrent_viewers ?? null,
            gpu_active:         d.gpu_active         ?? false,
          } satisfies Live
        })

        // Ordem estavel: novos IDs vao para o final, existentes mantem posicao
        const newIds = data.map((l) => l.video_id).filter((id) => !orderRef.current.includes(id))
        orderRef.current = [...orderRef.current, ...newIds]
        setLives(
          [...data].sort(
            (a, b) => orderRef.current.indexOf(a.video_id) - orderRef.current.indexOf(b.video_id)
          )
        )
      },
      () => setConnected(false)
    )
    return () => unsub()
  }, [])

  const STALE_MS = 5 * 60 * 1000
  const activeAll = lives.filter((l) => {
    if (l.status !== "active") return false
    if (hidden.has(l.video_id)) return false
    if (!l.last_seen_at) return true
    return Date.now() - new Date(l.last_seen_at).getTime() < STALE_MS
  })

  const selectedList = CHANNELS.filter((ch) => selectedChannels[ch])
  const active = selectedList.length === 0
    ? []
    : activeAll.filter((l) => selectedList.includes((l.channel || "").toUpperCase() as ChannelName))

  // Ordenação
  const sorted = sortMode === "split-lr" ? active : sortLives(active, sortMode, manualOrder)
  const pinned   = sorted.filter((l) => pinnedIds.includes(l.video_id))
  const unpinned = sorted.filter((l) => !pinnedIds.includes(l.video_id))

  // Split-LR
  const cazeLives = active.filter((l) => l.channel.toUpperCase() === "CAZETV")
  const getvLives = active.filter((l) => l.channel.toUpperCase() === "GETV")

  const handleDrop = useCallback((fromId: string, toId: string) => {
    reorder(fromId, toId)
    setDraggingId(null)
    setDragOverId(null)
  }, [reorder])

  const renderCard = (live: Live, liveCount: number) => (
    <LiveCard
      key={live.video_id}
      live={live}
      liveCount={liveCount}
      isPinned={pinnedIds.includes(live.video_id)}
      onPin={() => togglePin(live.video_id)}
      onDismiss={() => hideCard(live.video_id)}
      isDragging={draggingId === live.video_id}
      isDragOver={dragOverId === live.video_id}
      onDragStart={() => setDraggingId(live.video_id)}
      onDragOver={(e: React.DragEvent) => { e.preventDefault(); setDragOverId(live.video_id) }}
      onDrop={(e: React.DragEvent) => { e.preventDefault(); if (draggingId && draggingId !== live.video_id) handleDrop(draggingId, live.video_id) }}
    />
  )

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="fade-up flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 flex-wrap">
          <Activity size={16} className="text-white/20" />
          <div>
            <h1 className="text-sm font-bold text-white">Painel de Controle</h1>
            <p className="text-[11px] text-white/20 font-mono">
              {active.length > 0
                ? `${active.length} stream${active.length > 1 ? "s" : ""} ao vivo`
                : selectedList.length === 0
                  ? "Nenhum canal selecionado"
                  : selectedList.length === 2
                    ? "Aguardando streams nos canais selecionados"
                    : `Aguardando streams em ${selectedList[0]}`}
            </p>
          </div>
        </div>
        <div
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-[10px] font-bold font-mono tracking-wider ${
            connected
              ? "text-emerald-400/80 bg-emerald-500/8 border border-emerald-500/15"
              : "text-red-400/80 bg-red-500/8 border border-red-500/15"
          }`}
        >
          {connected ? <Wifi size={10} /> : <WifiOff size={10} />}
          {connected ? "ONLINE" : "OFFLINE"}
        </div>
      </div>

      {/* Toolbar de organização */}
      {active.length > 1 && (
        <LayoutToolbar
          sortMode={sortMode}
          onSortChange={setSortMode}
          pinnedCount={pinned.length}
        />
      )}

      {/* Cards fixados no topo */}
      {active.length > 0 && pinned.length > 0 && (
        <div className="fade-d1 space-y-1">
          <p className="text-[8px] font-mono text-amber-400/40 uppercase tracking-widest flex items-center gap-1.5">
            <Pin size={7} /> Fixados ({pinned.length})
          </p>
          <div className={pinnedGridClass(pinned.length, active.length)}>
            {pinned.map((live) => renderCard(live, active.length))}
          </div>
        </div>
      )}

      {/* Grid principal */}
      {active.length > 0 && (
        sortMode === "split-lr" ? (
          <div className="fade-d1 flex gap-4">
            <div className="flex-1 space-y-2 min-w-0">
              <p className="text-[9px] font-mono text-white/25 uppercase tracking-widest">CazeTV</p>
              <div className={innerGridClass(cazeLives.length)}>
                {cazeLives.map((live) => renderCard(live, active.length))}
              </div>
            </div>
            <div className="flex-1 space-y-2 min-w-0">
              <p className="text-[9px] font-mono text-emerald-400/35 uppercase tracking-widest">ge.tv</p>
              <div className={innerGridClass(getvLives.length)}>
                {getvLives.map((live) => renderCard(live, active.length))}
              </div>
            </div>
          </div>
        ) : (
          unpinned.length > 0 && (() => {
            if (pinned.length === 0) {
              return (
                <div className={`fade-d1 ${gridClass(unpinned.length)}`}>
                  {unpinned.map((live) => renderCard(live, active.length))}
                </div>
              )
            }
            const gap = gapFor(active.length)
            const [fullRows, lastRow] = splitUnpinned(unpinned)
            return (
              <div className={`fade-d1 flex flex-col ${gap}`}>
                {fullRows.length > 0 && (
                  <div className={`grid grid-cols-5 ${gap}`}>
                    {fullRows.map((live) => renderCard(live, active.length))}
                  </div>
                )}
                {lastRow.length > 0 && (
                  <div className={`grid grid-cols-${lastRow.length} ${gap}`}>
                    {lastRow.map((live) => renderCard(live, active.length))}
                  </div>
                )}
              </div>
            )
          })()
        )
      )}

      {/* Empty state */}
      {connected && active.length === 0 && (
        <div className="fade-d1 panel flex flex-col items-center justify-center py-16 text-center">
          <Tv2 size={32} className="text-white/6 mb-3" />
          <p className="text-white/25 text-xs font-medium">
            {selectedList.length === 0
              ? "Selecione pelo menos um canal"
              : selectedList.length === 1
                ? `Nenhum stream ativo em ${selectedList[0]}`
                : "Nenhum stream ativo nos canais selecionados"}
          </p>
          <p className="text-white/12 text-[11px] mt-1 font-mono">O monitor detectara automaticamente</p>
        </div>
      )}
    </div>
  )
}

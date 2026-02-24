"use client"

import { useEffect, useRef, useState } from "react"
import { collection, onSnapshot } from "firebase/firestore"
import { db } from "@/lib/firebase"
import { Live } from "@/lib/types"
import LiveCard from "@/components/LiveCard"
import { Tv2, Wifi, WifiOff, Activity } from "lucide-react"
import { useChannels } from "@/lib/channel-context"
import type { ChannelName } from "@/lib/channel-context"

const CHANNELS: ChannelName[] = ["CAZETV", "GETV"]

export default function HomePage() {
  const [lives, setLives]         = useState<Live[]>([])
  const [connected, setConnected] = useState(false)
  const [hidden, setHidden]       = useState<Set<string>>(new Set())
  const { selected: selectedChannels } = useChannels()
  const orderRef = useRef<string[]>([])

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

  const STALE_MS = 5 * 60 * 1000 // 5 min sem atualizacao do backend = live encerrada
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

  // Grid por quantidade de lives
  const gridCols =
    active.length <= 1 ? "" :
    active.length === 2 ? "grid grid-cols-2 gap-4" :
    active.length === 3 ? "grid grid-cols-3 gap-3" :
    active.length === 4 ? "grid grid-cols-2 gap-3" :
    active.length <= 6  ? "grid grid-cols-3 gap-2" :
    active.length <= 8  ? "grid grid-cols-4 gap-2" :
    "grid grid-cols-5 gap-2"

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

      {/* Active streams */}
      {active.length > 0 && (
        <div className={`fade-d1 ${gridCols}`}>
          {active.map((live) => (
            <LiveCard
              key={live.video_id}
              live={live}
              liveCount={active.length}
              onDismiss={() => hideCard(live.video_id)}
            />
          ))}
        </div>
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

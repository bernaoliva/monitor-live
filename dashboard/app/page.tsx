"use client"

import { useEffect, useRef, useState } from "react"
import Image from "next/image"
import { collection, onSnapshot } from "firebase/firestore"
import { db } from "@/lib/firebase"
import { Live } from "@/lib/types"
import LiveCard from "@/components/LiveCard"
import { Tv2, Wifi, WifiOff, Activity } from "lucide-react"

type ChannelName = "CAZETV" | "GETV"

const CHANNELS: ChannelName[] = ["CAZETV", "GETV"]
const CHANNEL_OPTIONS: Record<ChannelName, { logo: string; alt: string }> = {
  CAZETV: { logo: "/cazetv-logo-branco.png", alt: "CazeTV" },
  GETV: { logo: "/getv-logo.png", alt: "ge.tv" },
}

export default function HomePage() {
  const [lives, setLives]         = useState<Live[]>([])
  const [connected, setConnected] = useState(false)
  const [hidden, setHidden]       = useState<Set<string>>(new Set())
  const [selectedChannels, setSelectedChannels] = useState<Record<ChannelName, boolean>>({
    CAZETV: true,
    GETV: true,
  })
  const orderRef                  = useRef<string[]>([])

  // Carrega IDs ocultos e filtros de canal do localStorage apenas no cliente
  useEffect(() => {
    try {
      setHidden(new Set(JSON.parse(localStorage.getItem("hidden_lives") ?? "[]")))
      const savedSelected = JSON.parse(localStorage.getItem("channel_selected") ?? "null")
      if (Array.isArray(savedSelected)) {
        const next: Record<ChannelName, boolean> = { CAZETV: false, GETV: false }
        for (const ch of savedSelected) {
          if (ch === "CAZETV" || ch === "GETV") next[ch as ChannelName] = true
        }
        setSelectedChannels(next)
      } else {
        // Compatibilidade com versao anterior
        const oldTab = localStorage.getItem("channel_tab")
        if (oldTab === "CAZETV") setSelectedChannels({ CAZETV: true, GETV: false })
        if (oldTab === "GETV") setSelectedChannels({ CAZETV: false, GETV: true })
      }
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

  // Grid: 1 col para 1 live, 2 cols para 2, 3 cols para 3+
  const gridCols =
    active.length <= 1 ? "" :
    active.length === 2 ? "grid grid-cols-2 gap-4 items-start" :
    active.length <= 6 ? "grid grid-cols-2 xl:grid-cols-3 gap-3 items-start" :
    "grid grid-cols-2 xl:grid-cols-4 gap-3 items-start"

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
          <div className="flex flex-wrap items-end gap-4 ml-1">
            {CHANNELS.map((ch) => (
              <button
                key={ch}
                onClick={() => {
                  setSelectedChannels((prev) => {
                    const next = { ...prev, [ch]: !prev[ch] }
                    try {
                      localStorage.setItem(
                        "channel_selected",
                        JSON.stringify(CHANNELS.filter((k) => next[k]))
                      )
                    } catch {}
                    return next
                  })
                }}
                title={CHANNEL_OPTIONS[ch].alt}
                aria-label={CHANNEL_OPTIONS[ch].alt}
                className={`transition-all ${
                  selectedChannels[ch]
                    ? "opacity-100 scale-100"
                    : "opacity-50 scale-95 hover:opacity-85 hover:scale-100"
                }`}
              >
                <Image
                  src={CHANNEL_OPTIONS[ch].logo}
                  alt={CHANNEL_OPTIONS[ch].alt}
                  width={120}
                  height={36}
                  className="w-[120px] h-[36px] object-contain"
                />
                <span className={`block mt-1 h-0.5 rounded-full transition-all ${
                  selectedChannels[ch] ? "bg-emerald-400/90" : "bg-transparent"
                }`} />
              </button>
            ))}
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
            <LiveCard key={live.video_id} live={live} onDismiss={() => hideCard(live.video_id)} />
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

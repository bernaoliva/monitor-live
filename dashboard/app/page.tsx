"use client"

import { useEffect, useState, useRef } from "react"
import { useSearchParams } from "next/navigation"
import { collection, onSnapshot } from "firebase/firestore"
import { db } from "@/lib/firebase"
import { Live } from "@/lib/types"
import LiveCard from "@/components/LiveCard"
import { Tv2, Wifi, WifiOff, Activity } from "lucide-react"

export default function HomePage() {
  const searchParams                = useSearchParams()
  const tv                          = searchParams.get("tv") === "true"
  const [lives, setLives]           = useState<Live[]>([])
  const [connected, setConnected]   = useState(false)
  const [hidden, setHidden]         = useState<Set<string>>(new Set())
  const orderRef                    = useRef<string[]>([])

  // Carrega IDs ocultos do localStorage apenas no cliente
  useEffect(() => {
    try {
      setHidden(new Set(JSON.parse(localStorage.getItem("hidden_lives") ?? "[]")))
    } catch {}
  }, [])

  const hideCard = (videoId: string) => {
    setHidden(prev => {
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
          } satisfies Live
        })

        // Ordem estável: novos IDs vão para o final, existentes mantêm posição
        const newIds = data.map(l => l.video_id).filter(id => !orderRef.current.includes(id))
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

  const STALE_MS = 5 * 60 * 1000 // 5 min sem atualização do backend = live encerrada
  const active = lives.filter((l) => {
    if (l.status !== "active") return false
    if (hidden.has(l.video_id)) return false
    if (!l.last_seen_at) return true
    return Date.now() - new Date(l.last_seen_at).getTime() < STALE_MS
  })

  // Grid: 1 col para 1 live, 2 cols para 2, 3 cols para 3+
  const gridCols =
    active.length <= 1 ? "" :
    active.length === 2 ? "grid grid-cols-2 gap-4 items-start" :
    "grid grid-cols-2 xl:grid-cols-3 gap-3 items-start"

  // Modo TV: tela cheia, sem header da página
  if (tv) {
    return (
      <div className="fixed inset-0 z-[60] bg-bg p-3 overflow-hidden">
        {/* Status bar minimalista */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <div className="relative w-1.5 h-1.5">
              <div className="absolute inset-0 rounded-full bg-red-500 pulse-dot" />
              <div className="absolute inset-0 rounded-full bg-red-500" />
            </div>
            <span className="text-[10px] font-bold text-white/40 font-mono tracking-wider">
              MONITOR — {active.length} stream{active.length !== 1 ? "s" : ""}
            </span>
          </div>
          <div className={`flex items-center gap-1 text-[9px] font-bold font-mono ${
            connected ? "text-emerald-400/60" : "text-red-400/60"
          }`}>
            {connected ? <Wifi size={8} /> : <WifiOff size={8} />}
            {connected ? "ONLINE" : "OFFLINE"}
          </div>
        </div>

        {active.length > 0 ? (
          <div className={`h-[calc(100vh-48px)] ${
            active.length === 1 ? "grid grid-cols-1" :
            active.length === 2 ? "grid grid-cols-2 gap-3" :
            active.length <= 4 ? "grid grid-cols-2 grid-rows-2 gap-3" :
            "grid grid-cols-3 grid-rows-2 gap-2"
          }`}>
            {active.map((live) => (
              <div key={live.video_id} className="overflow-hidden min-h-0">
                <LiveCard live={live} compact onDismiss={() => hideCard(live.video_id)} />
              </div>
            ))}
          </div>
        ) : (
          <div className="h-[calc(100vh-48px)] flex flex-col items-center justify-center text-center">
            <Tv2 size={48} className="text-white/6 mb-3" />
            <p className="text-white/25 text-sm font-medium">Aguardando streams</p>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="fade-up flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Activity size={16} className="text-white/20" />
          <div>
            <h1 className="text-sm font-bold text-white">Painel de Controle</h1>
            <p className="text-[11px] text-white/20 font-mono">
              {active.length > 0
                ? `${active.length} stream${active.length > 1 ? "s" : ""} ao vivo`
                : "Aguardando streams"}
            </p>
          </div>
        </div>
        <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-[10px] font-bold font-mono tracking-wider ${
          connected
            ? "text-emerald-400/80 bg-emerald-500/8 border border-emerald-500/15"
            : "text-red-400/80 bg-red-500/8 border border-red-500/15"
        }`}>
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
          <p className="text-white/25 text-xs font-medium">Nenhum stream ativo</p>
          <p className="text-white/12 text-[11px] mt-1 font-mono">O monitor detectará automaticamente</p>
        </div>
      )}
    </div>
  )
}

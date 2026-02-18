"use client"

import { useEffect, useState, useRef } from "react"
import { collection, onSnapshot } from "firebase/firestore"
import { db } from "@/lib/firebase"
import { Live } from "@/lib/types"
import LiveCard from "@/components/LiveCard"
import { Tv2, Wifi, WifiOff, Activity } from "lucide-react"

export default function HomePage() {
  const [lives, setLives]         = useState<Live[]>([])
  const [connected, setConnected] = useState(false)
  const [hidden, setHidden]       = useState<Set<string>>(new Set())
  const orderRef                  = useRef<string[]>([])

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
        <div className={`fade-d1 ${active.length > 1 ? "grid grid-cols-2 gap-4 items-start" : "space-y-4"}`}>
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

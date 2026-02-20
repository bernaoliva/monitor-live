"use client"

import { useEffect, useState } from "react"
import { collection, onSnapshot } from "firebase/firestore"
import { db } from "@/lib/firebase"
import { Live } from "@/lib/types"
import HistoricoCard from "@/components/HistoricoCard"
import { History } from "lucide-react"

export default function HistoricoPage() {
  const [lives, setLives] = useState<Live[]>([])

  useEffect(() => {
    const unsub = onSnapshot(collection(db, "lives"), (snap) => {
      const data = snap.docs
        .map((doc) => {
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
            title_history:      d.title_history      ?? [],
          } satisfies Live
        })
        // Fallback: alguns docs antigos podem ter ended_at preenchido com status inconsistente.
        .filter((l) => l.status === "ended" || !!l.ended_at)
        .sort((a, b) => {
          const aTime = a.ended_at ?? a.started_at ?? ""
          const bTime = b.ended_at ?? b.started_at ?? ""
          return bTime.localeCompare(aTime)
        })
      setLives(data)
    })
    return () => unsub()
  }, [])

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="fade-up flex items-center gap-3">
        <History size={16} className="text-white/20" />
        <div>
          <h1 className="text-sm font-bold text-white">Historico</h1>
          <p className="text-[11px] text-white/20 font-mono">
            {lives.length > 0
              ? `${lives.length} transmiss${lives.length > 1 ? "oes" : "ao"} encerrada${lives.length > 1 ? "s" : ""}`
              : "Nenhuma transmissao encerrada"}
          </p>
        </div>
      </div>

      {/* Ended lives */}
      {lives.length > 0 ? (
        <div className="space-y-4 fade-d1">
          {lives.map((live) => (
            <HistoricoCard key={live.video_id} live={live} />
          ))}
        </div>
      ) : (
        <div className="fade-d1 panel flex flex-col items-center justify-center py-16 text-center">
          <History size={32} className="text-white/6 mb-3" />
          <p className="text-white/25 text-xs font-medium">Nenhuma transmissao encerrada</p>
          <p className="text-white/12 text-[11px] mt-1 font-mono">Lives encerradas aparecerao aqui</p>
        </div>
      )}
    </div>
  )
}

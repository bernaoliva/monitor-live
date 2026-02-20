"use client"

import { useEffect, useState, useMemo, useRef } from "react"
import Link from "next/link"
import {
  collection, onSnapshot, query, where,
  doc, updateDoc, increment,
} from "firebase/firestore"
import { db } from "@/lib/firebase"
import { Live, Comment, ChartPoint } from "@/lib/types"
import CommentsChart from "@/components/CommentsChart"
import { Youtube, AlertTriangle, ArrowRight, X } from "lucide-react"
import { format } from "date-fns"


function normalizeCategory(raw: string | null | undefined): string | null {
  if (!raw) return null
  const u = raw.toUpperCase().trim()
  if (/AUDIO|ÁUDIO|SOM\b|NARR/.test(u)) return "AUDIO"
  if (/VIDEO|VÍDEO|TELA|PIXEL|IMAG|CONGEL/.test(u)) return "VIDEO"
  if (/REDE|PLATAFORMA|BUFFER|CAIU|PLAT/.test(u)) return "REDE"
  if (/\bGC\b|PLACAR/.test(u)) return "GC"
  return u
}

const SEV_DOT: Record<string, string> = {
  high:   "bg-red-400",
  medium: "bg-amber-400",
  low:    "bg-yellow-300",
  none:   "bg-white/20",
}

type CatStyleEntry = {
  bg: string; text: string; border: string
  leftBar: string
  barColor: string
}

const CAT_STYLE: Record<string, CatStyleEntry> = {
  AUDIO: { bg: "bg-blue-500/10",   text: "text-blue-300",   border: "border-blue-500/20",   leftBar: "bg-blue-400/50",   barColor: "#60a5fa" },
  VIDEO: { bg: "bg-purple-500/10", text: "text-purple-300", border: "border-purple-500/20", leftBar: "bg-purple-400/50", barColor: "#c084fc" },
  REDE:  { bg: "bg-orange-500/10", text: "text-orange-300", border: "border-orange-500/20", leftBar: "bg-orange-400/50", barColor: "#fb923c" },
  GC:    { bg: "bg-cyan-500/10",   text: "text-cyan-300",   border: "border-cyan-500/20",   leftBar: "bg-cyan-400/50",   barColor: "#22d3ee" },
}
const CAT_DEFAULT: CatStyleEntry = {
  bg: "bg-white/[0.04]", text: "text-white/50", border: "border-white/[0.06]",
  leftBar: "bg-white/15", barColor: "rgba(255,255,255,0.2)",
}

export default function LiveCard({
  live,
  onDismiss,
  compact = false,
}: {
  live: Live
  onDismiss?: () => void
  compact?: boolean
}) {
  const [chartData,     setChartData]     = useState<ChartPoint[]>([])
  const [allTechComments, setAllTechComments] = useState<Comment[]>([])
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  const [alertKey, setAlertKey] = useState(0)
  const techSnapshotReadyRef = useRef(false)

  const minuteKeyFromTs = (ts: string): string | null => {
    try {
      const dt = new Date(ts.includes("T") ? ts : ts.replace(" ", "T"))
      if (Number.isNaN(dt.getTime())) return null
      return format(dt, "HH:mm")
    } catch {
      return null
    }
  }

  // Carrega dismissed do localStorage ao montar
  useEffect(() => {
    try {
      const stored = localStorage.getItem(`dismissed_${live.video_id}`)
      if (stored) setDismissed(new Set(JSON.parse(stored)))
    } catch {}
  }, [live.video_id])

  // Descarta localmente + persiste no localStorage + marca como não-técnico no Firestore
  const dismissComment = async (c: Comment) => {
    const minuteKey = minuteKeyFromTs(c.ts)

    if (minuteKey) {
      setChartData((prev) =>
        prev.map((p) =>
          p.minute === minuteKey
            ? { ...p, technical: Math.max(0, (p.technical ?? 0) - 1) }
            : p
        )
      )
    }

    setDismissed(prev => {
      const next = new Set([...prev, c.id])
      try { localStorage.setItem(`dismissed_${live.video_id}`, JSON.stringify([...next])) } catch {}
      return next
    })
    try {
      await updateDoc(doc(db, "lives", live.video_id, "comments", c.id), {
        is_technical: false,
      })
      const liveUpdate: Record<string, unknown> = {
        technical_comments: increment(-1),
      }
      if (c.category && c.issue) {
        liveUpdate[`issue_counts.${c.category}:${c.issue}`] = increment(-1)
      }
      await updateDoc(doc(db, "lives", live.video_id), liveUpdate)
      if (minuteKey) {
        await updateDoc(
          doc(db, "lives", live.video_id, "minutes", minuteKey),
          { technical: increment(-1) }
        )
      }
    } catch (e) {
      console.error("Erro ao descartar comentário:", e)
    }
  }

  useEffect(() => {
    // Chart: lê agregados por minuto (leve — ~200 docs em vez de 50k+)
    const qMinutes = query(
      collection(db, "lives", live.video_id, "minutes"),
    )
    const unsub = onSnapshot(qMinutes, (snap) => {
      setChartData(
        snap.docs
          .filter((d) => /^\d{2}:\d{2}$/.test(d.id))  // ignora chaves inválidas
          .map((d) => {
            const raw = d.data()
            return {
              minute:    d.id,
              total:     raw.total     ?? 0,
              technical: raw.technical ?? 0,
            } satisfies ChartPoint
          })
          .sort((a, b) => a.minute.localeCompare(b.minute))
      )
    })

    // Feed: todos os técnicos — igual ao detail page (where sem orderBy, sem índice composto)
    techSnapshotReadyRef.current = false
    const qTech = query(
      collection(db, "lives", live.video_id, "comments"),
      where("is_technical", "==", true)
    )
    const unsubTech = onSnapshot(qTech, (snap) => {
      const hasNewTech = techSnapshotReadyRef.current && snap.docChanges().some((ch) => ch.type === "added")
      setAllTechComments(
        snap.docs
          .map((d) => {
            const raw = d.data()
            return {
              id:           d.id,
              author:       raw.author       ?? "",
              text:         raw.text         ?? "",
              ts:           raw.ts           ?? "",
              is_technical: raw.is_technical ?? false,
              category:     raw.category     ?? null,
              issue:        raw.issue        ?? null,
              severity:     raw.severity     ?? "none",
            } satisfies Comment
          })
      )
      if (hasNewTech) {
        setAlertKey((k) => k + 1)
      }
      techSnapshotReadyRef.current = true
    }, (err) => console.error("[LiveCard] tech feed error:", err))

    return () => { unsub(); unsubTech() }
  }, [live.video_id])

  // Feed: todos os técnicos, newest first, excluindo dismissed
  const visibleComments = useMemo(() =>
    [...allTechComments]
      .filter((c) => !dismissed.has(c.id))
      .sort((a, b) => b.ts.localeCompare(a.ts)),
    [allTechComments, dismissed]
  )

  const chartDataDisplay = useMemo(() => {
    const techByMinute: Record<string, number> = {}
    for (const c of visibleComments) {
      const mk = minuteKeyFromTs(c.ts)
      if (!mk) continue
      techByMinute[mk] = (techByMinute[mk] ?? 0) + 1
    }
    return chartData
      .map((p) => ({
        ...p,
        technical: techByMinute[p.minute] ?? 0,
      }))
      .sort((a, b) => a.minute.localeCompare(b.minute))
  }, [chartData, visibleComments])

  // Alerta flash quando surge novo problema técnico
  const lastFiveComments = visibleComments

  // Usa contadores do documento live (não dos comentários limitados)
  const totalTechCount = visibleComments.length
  const techRate = Math.round(
    (totalTechCount / Math.max(live.total_comments, 1)) * 100
  )

  // Categorias: computa dos comentários técnicos visíveis — igual ao detail page
  const categoryBreakdown = useMemo(() => {
    const acc: Record<string, number> = {}
    visibleComments.forEach((c) => {
      const cat = normalizeCategory(c.category)
      if (cat) acc[cat] = (acc[cat] || 0) + 1
    })
    return Object.entries(acc)
      .filter(([, c]) => c > 0)
      .sort(([, a], [, b]) => b - a)
  }, [visibleComments])

  const categoryTotal = categoryBreakdown.reduce((s, [, c]) => s + c, 0)

  const alertBorder =
    techRate > 15 ? "border-red-500/40" :
    techRate > 5  ? "border-amber-500/25" :
    ""

  // Cores do flash por categoria (fill, borda luminosa)
  const lastCat = lastFiveComments[0] ? normalizeCategory(lastFiveComments[0].category) : null
  const flashFill   = lastCat === "AUDIO" ? "rgba(96,165,250,0.55)"
    : lastCat === "VIDEO" ? "rgba(192,132,252,0.55)"
    : lastCat === "REDE"  ? "rgba(251,146,60,0.55)"
    : lastCat === "GC"    ? "rgba(34,211,238,0.55)"
    : "rgba(239,68,68,0.55)"
  const flashBorder = lastCat === "AUDIO" ? "rgba(96,165,250,0.9)"
    : lastCat === "VIDEO" ? "rgba(192,132,252,0.9)"
    : lastCat === "REDE"  ? "rgba(251,146,60,0.9)"
    : lastCat === "GC"    ? "rgba(34,211,238,0.9)"
    : "rgba(239,68,68,0.9)"

  return (
    <div className={`panel overflow-hidden relative ${alertBorder}`}>

      {/* Flash ao detectar novo problema — 3 pulsadas + borda luminosa */}
      {alertKey > 0 && (
        <div
          key={alertKey}
          className="absolute inset-0 z-10 alert-flash rounded-lg"
          style={{
            background: `linear-gradient(180deg, ${flashFill} 0%, rgba(0,0,0,0) 75%)`,
            boxShadow: `inset 0 0 0 2px ${flashBorder}`,
          }}
        />
      )}

      {/* Header */}
      <div className="flex items-start justify-between px-4 pt-4 pb-3">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-center gap-2">
            <div className="relative w-1.5 h-1.5">
              <div className="absolute inset-0 rounded-full bg-emerald-400 pulse-dot" />
              <div className="absolute inset-0 rounded-full bg-emerald-400" />
            </div>
            <span className="tag bg-emerald-500/15 text-emerald-400 border border-emerald-500/20">
              AO VIVO
            </span>
            {live.gpu_active && (
              <span className="tag bg-violet-500/20 text-violet-300 border border-violet-500/30">
                GPU
              </span>
            )}
          </div>
          <h3 className="font-bold text-white text-sm leading-snug line-clamp-2 pr-4">
            {live.title || live.video_id}
          </h3>
          {live.url && (
            <a
              href={live.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-[10px] font-bold font-mono text-red-400/80 hover:text-red-300 transition-colors w-fit"
              title="Abrir live no YouTube"
            >
              <Youtube size={12} />
              YOUTUBE
            </a>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0 pt-0.5">
          <Link
            href={`/live/${live.video_id}`}
            className="flex items-center gap-1 text-[10px] font-bold font-mono text-white/35 hover:text-white/65 transition-colors"
          >
            ABRIR <ArrowRight size={10} />
          </Link>
          {onDismiss && (
            <button
              onClick={onDismiss}
              title="Ocultar este card"
              className="text-white/25 hover:text-red-400/70 transition-colors ml-0.5"
            >
              <X size={12} />
            </button>
          )}
        </div>
      </div>

      {/* Stats strip */}
      <div className="grid grid-cols-4 border-y border-white/[0.06]">
        <div className="px-3 py-2.5">
          <p className="text-[8px] font-bold uppercase tracking-wider text-white/40 mb-1">Msgs</p>
          <p className="font-data text-base font-black text-white">
            {(live.total_comments || 0).toLocaleString()}
          </p>
        </div>
        <div className="px-3 py-2.5 border-l border-white/[0.06]">
          <p className="text-[8px] font-bold uppercase tracking-wider text-white/40 mb-1">Problemas</p>
          <p className={`font-data text-base font-black ${
            techRate > 15 ? "text-red-400" : techRate > 5 ? "text-amber-400" : "text-emerald-400"
          }`}>
            {totalTechCount.toLocaleString()}
          </p>
        </div>
        <div className="px-3 py-2.5 border-l border-white/[0.06]">
          <p className="text-[8px] font-bold uppercase tracking-wider text-white/40 mb-1">Audiência</p>
          <p className="font-data text-base font-black text-white/80">
            {live.concurrent_viewers != null
              ? live.concurrent_viewers >= 1_000_000
                ? `${(live.concurrent_viewers / 1_000_000).toFixed(1)}M`
                : live.concurrent_viewers >= 1_000
                ? `${(live.concurrent_viewers / 1_000).toFixed(0)}k`
                : live.concurrent_viewers.toString()
              : "—"}
          </p>
        </div>
        <div className="px-3 py-2.5 border-l border-white/[0.06]">
          <p className="text-[8px] font-bold uppercase tracking-wider text-white/40 mb-1">Categorias</p>
          <p className="font-data text-base font-black text-white/60">
            {categoryBreakdown.length}
          </p>
        </div>
      </div>

      {/* Chart */}
      <div className="px-4 pt-1 pb-0">
        <CommentsChart data={chartDataDisplay} height={200} showLegend={false} />
      </div>

      {/* Abaixo do gráfico: comentários (2/3) + categorias (1/3) */}
      <div className="border-t border-white/[0.06] flex min-h-0">

        {/* Coluna esquerda: últimos 5 comentários técnicos */}
        <div className="flex-[4] min-w-0 border-r border-white/[0.06]">
          <div className="px-3 py-2 flex items-center gap-1.5 border-b border-white/[0.04]">
            <AlertTriangle size={9} className="text-red-400/60 shrink-0" />
            <span className="text-[8px] font-bold font-mono uppercase tracking-wider text-white/40">
              Últimos problemas
            </span>
            <span className="font-data text-[9px] text-white/30 ml-auto">{visibleComments.length}</span>
          </div>
          <div className="max-h-[200px] overflow-y-scroll flex flex-col justify-start comments-scroll">
            {visibleComments.length === 0 ? (
              <div className="px-3 py-4 text-[10px] text-white/25 font-mono">
                Nenhum problema detectado
              </div>
            ) : (
              lastFiveComments.map((c) => {
                const catKey   = normalizeCategory(c.category) ?? ""
                const catStyle = CAT_STYLE[catKey] ?? CAT_DEFAULT
                return (
                  <div
                    key={c.id}
                    className={`relative group flex items-start gap-2 px-3 py-1.5 border-b border-white/[0.03] last:border-0 hover:bg-white/[0.02] transition-colors`}
                  >
                    <div className={`absolute left-0 top-0 bottom-0 w-0.5 ${catStyle.leftBar}`} />
                    <span className={`block w-1.5 h-1.5 rounded-full shrink-0 mt-1 ${SEV_DOT[c.severity] ?? SEV_DOT.none}`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        {catKey && (
                          <span className={`text-[8px] font-bold font-mono shrink-0 ${catStyle.text}`}>
                            {catKey}
                          </span>
                        )}
                        <span className="text-[8px] text-white/35 font-mono truncate">
                          {c.author}
                        </span>
                        <span className="text-[10px] text-white/70 font-mono font-bold shrink-0 ml-auto">
                          {format(new Date(c.ts.replace(" ", "T")), "HH:mm:ss")}
                        </span>
                      </div>
                      <span className="text-[11px] text-white/65 break-words leading-tight -mt-px block">
                        {c.text}
                      </span>
                    </div>
                    <button
                      onClick={() => dismissComment(c)}
                      title="Descartar"
                      className="opacity-0 group-hover:opacity-100 transition-opacity shrink-0 text-white/25 hover:text-red-400/70 mt-0.5"
                    >
                      <X size={9} />
                    </button>
                  </div>
                )
              })
            )}
          </div>
          <div className="px-3 py-1.5 flex items-center justify-end border-t border-white/[0.04]">
            <Link
              href={`/live/${live.video_id}`}
              className="text-[9px] font-mono font-bold text-white/25 hover:text-white/50 transition-colors flex items-center gap-1"
            >
              ver tudo <ArrowRight size={8} />
            </Link>
          </div>
        </div>

        {/* Coluna direita: barras de categoria */}
        <div className="flex-[1] min-w-0 px-3 py-2.5 space-y-2.5">
          <p className="text-[8px] font-bold uppercase tracking-wider text-white/40">
            Por categoria
          </p>
          {categoryBreakdown.length === 0 ? (
            <p className="text-[10px] text-white/20 font-mono">—</p>
          ) : (
            categoryBreakdown.map(([cat, count]) => {
              const style = CAT_STYLE[cat] ?? CAT_DEFAULT
              const pct   = Math.round((count / Math.max(categoryTotal, 1)) * 100)
              return (
                <div key={cat} className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className={`text-[8px] font-bold font-mono uppercase ${style.text}`}>
                      {cat}
                    </span>
                    <span className={`font-data text-[10px] font-bold ${style.text}`}>
                      {count}
                    </span>
                  </div>
                  <div className="h-1 bg-white/[0.06] rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-700"
                      style={{ width: `${pct}%`, background: style.barColor }}
                    />
                  </div>
                </div>
              )
            })
          )}
        </div>

      </div>
    </div>
  )
}

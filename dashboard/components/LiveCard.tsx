"use client"

import { useEffect, useState, useMemo } from "react"
import Link from "next/link"
import {
  collection, onSnapshot, query, orderBy, where,
  doc, updateDoc, increment,
} from "firebase/firestore"
import { db } from "@/lib/firebase"
import { Live, Comment, ChartPoint } from "@/lib/types"
import CommentsChart from "@/components/CommentsChart"
import { ExternalLink, AlertTriangle, ArrowRight, X, ChevronDown, ChevronUp, Minus, Plus } from "lucide-react"
import { format } from "date-fns"

function buildChartData(comments: Comment[]): ChartPoint[] {
  const buckets: Record<string, { total: number; technical: number }> = {}
  comments.forEach((c) => {
    const minute = format(new Date(c.ts), "HH:mm")
    if (!buckets[minute]) buckets[minute] = { total: 0, technical: 0 }
    buckets[minute].total++
    if (c.is_technical) buckets[minute].technical++
  })
  return Object.entries(buckets)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([minute, v]) => ({ minute, ...v }))
}

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
  leftBar: string  // cor para a barra lateral esquerda
  barColor: string // cor hex para a barra de progresso
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
}: {
  live: Live
  onDismiss?: () => void
}) {
  const [comments,      setComments]      = useState<Comment[]>([])
  const [allTechComments, setAllTechComments] = useState<Comment[]>([])
  const [dismissed,     setDismissed]     = useState<Set<string>>(new Set())
  const [expanded,      setExpanded]      = useState(false)
  const [feedMinimized, setFeedMinimized] = useState(false)

  // Carrega dismissed do localStorage ao montar
  useEffect(() => {
    try {
      const stored = localStorage.getItem(`dismissed_${live.video_id}`)
      if (stored) setDismissed(new Set(JSON.parse(stored)))
    } catch {}
  }, [live.video_id])

  // Descarta localmente + persiste no localStorage + marca como não-técnico no Firestore
  const dismissComment = async (c: Comment) => {
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
    } catch (e) {
      console.error("Erro ao descartar comentário:", e)
    }
  }

  useEffect(() => {
    const q = query(
      collection(db, "lives", live.video_id, "comments"),
      orderBy("ts", "asc")
    )
    const unsub = onSnapshot(q, (snap) => {
      setComments(
        snap.docs.map((d) => {
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
    })

    // Query idêntica à da página de detalhe — todos os técnicos da transmissão
    const qTech = query(
      collection(db, "lives", live.video_id, "comments"),
      where("is_technical", "==", true)
    )
    const unsubTech = onSnapshot(qTech, (snap) => {
      setAllTechComments(
        snap.docs.map((d) => {
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
    })

    return () => { unsub(); unsubTech() }
  }, [live.video_id])

  const techComments    = comments.filter((c) => c.is_technical)

  // Feed: all technical comments (not just last 200), sorted newest first, excluding dismissed
  const visibleComments = useMemo(() =>
    [...allTechComments]
      .filter((c) => !dismissed.has(c.id))
      .sort((a, b) => b.ts.localeCompare(a.ts)),
    [allTechComments, dismissed]
  )

  const RECENT_COUNT = 8
  const recentComments = visibleComments.slice(0, RECENT_COUNT)
  const olderComments  = visibleComments.slice(RECENT_COUNT)

  // Gráfico: aplica dismissed imediatamente sem esperar o Firestore
  const chartData = useMemo(() => {
    const adjusted = comments.map((c) =>
      dismissed.has(c.id) ? { ...c, is_technical: false } : c
    )
    return buildChartData(adjusted)
  }, [comments, dismissed])

  // Mesma fonte de verdade da página de detalhe
  const totalTechCount = allTechComments.filter(c => !dismissed.has(c.id)).length
  const techRate = Math.round(
    (totalTechCount / Math.max(live.total_comments, 1)) * 100
  )

  // Problemas citados: conta diretamente dos comentários técnicos visíveis
  const categoryBreakdown = useMemo(() => {
    const acc: Record<string, number> = {}
    visibleComments.forEach((c) => {
      const cat = normalizeCategory(c.category)
      if (cat) {
        acc[cat] = (acc[cat] || 0) + 1
      }
    })
    return Object.entries(acc)
      .filter(([, c]) => c > 0)
      .sort(([, a], [, b]) => b - a)
  }, [visibleComments])

  const categoryTotal = categoryBreakdown.reduce((s, [, c]) => s + c, 0)

  // Cor de alerta do card baseada na taxa de problemas
  const alertBorder =
    techRate > 15 ? "border-red-500/40" :
    techRate > 5  ? "border-amber-500/25" :
    ""

  return (
    <div className={`panel overflow-hidden ${alertBorder}`}>

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
          </div>
          <h3 className="font-bold text-white text-sm leading-snug line-clamp-2 pr-4">
            {live.title || live.video_id}
          </h3>
        </div>
        <div className="flex items-center gap-2 shrink-0 pt-0.5">
          {live.url && (
            <a
              href={live.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-white/30 hover:text-white/60 transition-colors"
            >
              <ExternalLink size={12} />
            </a>
          )}
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
          <p className="text-[8px] font-bold uppercase tracking-wider text-white/40 mb-1">Taxa</p>
          <p className={`font-data text-base font-black ${
            techRate > 15 ? "text-red-400" : techRate > 5 ? "text-amber-400" : "text-emerald-400"
          }`}>
            {techRate}%
          </p>
        </div>
        <div className="px-3 py-2.5 border-l border-white/[0.06]">
          <p className="text-[8px] font-bold uppercase tracking-wider text-white/40 mb-1">Categorias</p>
          <p className="font-data text-base font-black text-white/60">
            {categoryBreakdown.length}
          </p>
        </div>
      </div>

      {/* Problemas citados — barras de proporção */}
      {categoryBreakdown.length > 0 && (
        <div className="px-4 py-3 border-b border-white/[0.06] space-y-2">
          <p className="text-[8px] font-bold uppercase tracking-wider text-white/40">
            Problemas citados
          </p>
          {categoryBreakdown.map(([cat, count]) => {
            const style = CAT_STYLE[cat] ?? CAT_DEFAULT
            const pct   = Math.round((count / Math.max(categoryTotal, 1)) * 100)
            return (
              <div key={cat} className="flex items-center gap-3">
                <span className={`text-[9px] font-bold font-mono uppercase w-16 shrink-0 ${style.text}`}>
                  {cat}
                </span>
                <div className="flex-1 h-1 bg-white/[0.06] rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{ width: `${pct}%`, background: style.barColor }}
                  />
                </div>
                <span className={`font-data text-[11px] font-bold w-7 text-right shrink-0 ${style.text}`}>
                  {count}
                </span>
              </div>
            )
          })}
        </div>
      )}

      {/* Chart */}
      <div className="px-4 pt-3 pb-1">
        <CommentsChart data={chartData} />
      </div>

      {/* Technical comments feed */}
      <div className="border-t border-white/[0.06]">
        <div className="px-4 py-2 flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <AlertTriangle size={10} className="text-red-400/60" />
            <span className="text-[9px] font-bold font-mono uppercase tracking-wider text-white/45">
              Problemas em tempo real
            </span>
            <span className="font-data text-[9px] text-white/35">{visibleComments.length}</span>
          </div>
          {visibleComments.length > 0 && (
            <button
              onClick={() => setFeedMinimized((v) => !v)}
              title={feedMinimized ? "Expandir feed" : "Minimizar feed"}
              className="text-white/25 hover:text-white/50 transition-colors"
            >
              {feedMinimized ? <Plus size={12} /> : <Minus size={12} />}
            </button>
          )}
        </div>

        {feedMinimized ? (
          <div className="px-4 pb-2 text-[10px] text-white/25 font-mono">
            Feed minimizado — {visibleComments.length} problema{visibleComments.length !== 1 ? "s" : ""} detectado{visibleComments.length !== 1 ? "s" : ""}
          </div>
        ) : visibleComments.length === 0 ? (
          <div className="px-4 pb-4 text-[11px] text-white/30 font-mono">
            Nenhum problema detectado
          </div>
        ) : (
          <>
            {/* Recent comments — expanded view */}
            <div>
              {recentComments.map((c) => {
                const catKey   = normalizeCategory(c.category) ?? ""
                const catStyle = CAT_STYLE[catKey] ?? CAT_DEFAULT
                return (
                  <div
                    key={c.id}
                    className="relative flex gap-3 group py-2.5 border-b border-white/[0.04] last:border-0"
                  >
                    <div className={`absolute left-0 top-0 bottom-0 w-0.5 ${catStyle.leftBar}`} />
                    <div className="pl-4 pr-1 flex gap-3 flex-1 min-w-0">
                      <div className="pt-1.5 shrink-0">
                        <span className={`block w-1.5 h-1.5 rounded-full ${SEV_DOT[c.severity] ?? SEV_DOT.none}`} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5 mb-1 flex-wrap">
                          {catKey && (
                            <span className={`inline-flex items-center px-1.5 py-0.5 rounded border text-[8px] font-bold font-mono tracking-wide ${catStyle.bg} ${catStyle.border} ${catStyle.text}`}>
                              {catKey}
                            </span>
                          )}
                          {c.severity && c.severity !== "none" && (
                            <span className={`text-[8px] font-bold px-1 py-0.5 rounded ${
                              c.severity === "high"   ? "bg-red-500/20 text-red-300" :
                              c.severity === "medium" ? "bg-amber-500/20 text-amber-300" :
                                                        "bg-yellow-500/20 text-yellow-300"
                            }`}>
                              {c.severity.toUpperCase()}
                            </span>
                          )}
                          <span className="text-[10px] font-semibold text-white/50 truncate max-w-[100px]">
                            {c.author}
                          </span>
                          <span className="text-[9px] text-white/30 font-mono shrink-0">
                            {format(new Date(c.ts), "HH:mm:ss")}
                          </span>
                        </div>
                        <p className="text-[12px] text-white/80 leading-relaxed">{c.text}</p>
                        {c.issue && (
                          <span className="inline-block mt-0.5 text-[8px] text-white/35 font-mono">
                            {c.issue}
                          </span>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={() => dismissComment(c)}
                      title="Descartar: marcar como não-técnico"
                      className="opacity-0 group-hover:opacity-100 transition-opacity shrink-0 mt-1.5 mr-3 text-white/25 hover:text-red-400/70"
                    >
                      <X size={10} />
                    </button>
                  </div>
                )
              })}
            </div>

            {/* Toggle button for older comments */}
            {olderComments.length > 0 && (
              <button
                onClick={() => setExpanded((v) => !v)}
                className="w-full px-4 py-2 flex items-center justify-center gap-1.5 border-y border-white/[0.04] text-[10px] font-mono font-bold text-white/30 hover:text-white/50 hover:bg-white/[0.02] transition-all"
              >
                {expanded ? (
                  <>Ocultar anteriores <ChevronUp size={10} /></>
                ) : (
                  <>+{olderComments.length} problema{olderComments.length > 1 ? "s" : ""} anterior{olderComments.length > 1 ? "es" : ""} <ChevronDown size={10} /></>
                )}
              </button>
            )}

            {/* Older comments — compact view */}
            {expanded && olderComments.length > 0 && (
              <div className="max-h-[400px] overflow-y-auto">
                {olderComments.map((c) => {
                  const catKey   = normalizeCategory(c.category) ?? ""
                  const catStyle = CAT_STYLE[catKey] ?? CAT_DEFAULT
                  return (
                    <div
                      key={c.id}
                      className="group flex items-center gap-2 px-4 py-1.5 border-b border-white/[0.03] last:border-0 hover:bg-white/[0.02] transition-colors"
                    >
                      <span className={`block w-1.5 h-1.5 rounded-full shrink-0 ${SEV_DOT[c.severity] ?? SEV_DOT.none}`} />
                      {catKey && (
                        <span className={`text-[8px] font-bold font-mono shrink-0 ${catStyle.text}`}>
                          {catKey}
                        </span>
                      )}
                      <span className="text-[11px] text-white/60 truncate flex-1 min-w-0">
                        {c.text}
                      </span>
                      <span className="text-[9px] text-white/25 font-mono shrink-0">
                        {format(new Date(c.ts), "HH:mm")}
                      </span>
                      <button
                        onClick={() => dismissComment(c)}
                        title="Descartar"
                        className="opacity-0 group-hover:opacity-100 transition-opacity shrink-0 text-white/25 hover:text-red-400/70"
                      >
                        <X size={10} />
                      </button>
                    </div>
                  )
                })}
              </div>
            )}
          </>
        )}

        {/* Footer */}
        <div className="px-4 py-2 flex items-center justify-end border-t border-white/[0.04]">
          <Link
            href={`/live/${live.video_id}`}
            className="text-[9px] font-mono font-bold text-white/25 hover:text-white/50 transition-colors flex items-center gap-1"
          >
            ver historico completo <ArrowRight size={8} />
          </Link>
        </div>
      </div>
    </div>
  )
}

"use client"

import { useEffect, useState, useMemo } from "react"
import Link from "next/link"
import { collection, onSnapshot, query, where, getDocs } from "firebase/firestore"
import { db } from "@/lib/firebase"
import { Live, Comment, ChartPoint } from "@/lib/types"
import CommentsChart from "@/components/CommentsChart"
import { ArrowRight } from "lucide-react"
import { format } from "date-fns"
import { computeHealthScore } from "@/lib/health-score"
import { parseCompetition } from "@/lib/title-parser"
import { TitleChange } from "@/lib/types"

function buildChartData(comments: Comment[]): ChartPoint[] {
  const buckets: Record<string, { total: number; technical: number }> = {}
  comments.forEach((c) => {
    const minute = format(new Date(c.ts.replace(" ", "T")), "HH:mm")
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

const CAT_STYLE: Record<string, { bg: string; text: string; border: string; barColor: string }> = {
  AUDIO: { bg: "bg-blue-500/10",   text: "text-blue-300",   border: "border-blue-500/20",   barColor: "#60a5fa" },
  VIDEO: { bg: "bg-purple-500/10", text: "text-purple-300", border: "border-purple-500/20", barColor: "#c084fc" },
  REDE:  { bg: "bg-orange-500/10", text: "text-orange-300", border: "border-orange-500/20", barColor: "#fb923c" },
  GC:    { bg: "bg-cyan-500/10",   text: "text-cyan-300",   border: "border-cyan-500/20",   barColor: "#22d3ee" },
}
const CAT_DEFAULT = {
  bg: "bg-white/[0.04]", text: "text-white/50", border: "border-white/[0.06]", barColor: "rgba(255,255,255,0.2)",
}

function formatDuration(startedAt: string, endedAt: string | null): string {
  if (!endedAt) return "—"
  const ms = new Date(endedAt).getTime() - new Date(startedAt).getTime()
  const h = Math.floor(ms / 3600000)
  const m = Math.floor((ms % 3600000) / 60000)
  if (h > 0) return `${h}h${m > 0 ? `${m}m` : ""}`
  return `${m}m`
}

export default function HistoricoCard({ live }: { live: Live }) {
  const [techComments, setTechComments] = useState<Comment[]>([])
  const [peakViewers, setPeakViewers]   = useState<number | null>(null)
  const [avgViewers,  setAvgViewers]    = useState<number | null>(null)

  useEffect(() => {
    getDocs(collection(db, "lives", live.video_id, "minutes")).then((snap) => {
      const vals = snap.docs
        .map((d) => d.data().viewers as number | undefined)
        .filter((v): v is number => typeof v === "number" && v > 0)
      if (vals.length) {
        setPeakViewers(Math.max(...vals))
        setAvgViewers(Math.round(vals.reduce((s, v) => s + v, 0) / vals.length))
      }
    })
  }, [live.video_id])

  useEffect(() => {
    const q = query(
      collection(db, "lives", live.video_id, "comments"),
      where("is_technical", "==", true)
    )
    const unsub = onSnapshot(q, (snap) => {
      setTechComments(
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
    return () => unsub()
  }, [live.video_id])

  const chartData = useMemo(() => buildChartData(techComments), [techComments])

  const techRate = Math.round(
    ((live.technical_comments || 0) / Math.max(live.total_comments, 1)) * 100
  )

  const healthScore = useMemo(
    () => computeHealthScore(
      live.concurrent_viewers ?? 0,
      techComments.map((c) => ({ ts: c.ts, severity: c.severity, issue: c.issue })),
      chartData,
    ),
    [live.concurrent_viewers, techComments, chartData],
  )

  // Conta diretamente dos comentários técnicos reais
  const categoryBreakdown = useMemo(() => {
    const acc: Record<string, number> = {}
    techComments.forEach((c) => {
      const cat = normalizeCategory(c.category)
      if (cat) {
        acc[cat] = (acc[cat] || 0) + 1
      }
    })
    return Object.entries(acc)
      .filter(([, c]) => c > 0)
      .sort(([, a], [, b]) => b - a)
  }, [techComments])

  const categoryTotal = categoryBreakdown.reduce((s, [, c]) => s + c, 0)

  const startDate = live.started_at
    ? format(new Date(live.started_at), "dd/MM HH:mm")
    : "—"

  // Todos os títulos com mesmo peso — usa title_changes (com timestamp) ou fallback title_history
  const allTitles: { title: string; ts?: string }[] = useMemo(() => {
    if (live.title_changes && live.title_changes.length > 0) {
      return [...live.title_changes].sort((a, b) => a.ts.localeCompare(b.ts))
    }
    const hist = live.title_history ?? [live.title]
    return hist.map((t) => ({ title: t }))
  }, [live.title, live.title_history, live.title_changes])

  // Competições únicas de todos os títulos
  const allCompetitions = useMemo(() => {
    const seen = new Set<string>()
    const result: string[] = []
    allTitles.forEach(({ title }) => {
      const comp = parseCompetition(title)
      if (comp !== "OUTROS" && !seen.has(comp)) { seen.add(comp); result.push(comp) }
    })
    return result
  }, [allTitles])

  const accentClass =
    healthScore.score >= 80 ? "accent-bar-green" :
    healthScore.score >= 50 ? "accent-bar-amber" : "accent-bar-red"

  return (
    <div className={`panel overflow-hidden ${accentClass}`}>
      {/* Header */}
      <div className="flex items-start justify-between px-4 pt-4 pb-3">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-center flex-wrap gap-1.5">
            <span className="tag bg-white/[0.04] text-white/35 border border-white/[0.06]">
              ENCERRADA
            </span>
            {allCompetitions.map((comp) => (
              <span key={comp} className="tag bg-white/[0.06] text-white/45 border border-white/[0.08]">
                {comp}
              </span>
            ))}
            <span className="text-[10px] text-white/25 font-mono">{startDate}</span>
            <span className="text-[10px] text-white/20 font-mono">
              {formatDuration(live.started_at, live.ended_at)}
            </span>
          </div>
          <div className="space-y-0.5 pt-0.5 pr-4">
            {allTitles.map(({ title }, i) => (
              <p key={i} className="font-bold text-white/80 text-sm leading-snug line-clamp-2">
                {title}
              </p>
            ))}
          </div>
        </div>
        <Link
          href={`/live/${live.video_id}`}
          className="flex items-center gap-1 text-[10px] font-bold font-mono text-white/35 hover:text-white/65 transition-colors shrink-0 pt-0.5"
        >
          ABRIR <ArrowRight size={10} />
        </Link>
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
            {(live.technical_comments || 0).toLocaleString()}
          </p>
        </div>
        <div className="px-3 py-2.5 border-l border-white/[0.06]">
          <p className="text-[8px] font-bold uppercase tracking-wider text-white/40 mb-1">Audiência</p>
          {peakViewers ? (
            <div className="space-y-0.5">
              <div className="flex items-baseline gap-1">
                <span className="text-[7px] text-white/30 font-mono uppercase">pico</span>
                <span className="font-data text-sm font-black text-white/70">{peakViewers.toLocaleString("pt-BR")}</span>
              </div>
              <div className="flex items-baseline gap-1">
                <span className="text-[7px] text-white/30 font-mono uppercase">média</span>
                <span className="font-data text-[11px] font-bold text-white/45">{avgViewers?.toLocaleString("pt-BR")}</span>
              </div>
            </div>
          ) : (
            <p className="font-data text-base font-black text-white/25">—</p>
          )}
        </div>
        <div className="px-3 py-2.5 border-l border-white/[0.06]">
          <p className="text-[8px] font-bold uppercase tracking-wider text-white/40 mb-1">Score</p>
          <p className="font-data text-base font-black" style={{ color: healthScore.color }}>
            {healthScore.score}
            <span className="text-[8px] font-mono ml-1 opacity-70">{healthScore.level}</span>
          </p>
        </div>
      </div>

      {/* Category bars */}
      {categoryBreakdown.length > 0 && (
        <div className="px-4 py-3 border-b border-white/[0.06] space-y-2">
          <p className="text-[8px] font-bold uppercase tracking-wider text-white/40">
            Problemas citados
          </p>
          {categoryBreakdown.map(([cat, count]) => {
            const style = CAT_STYLE[cat] ?? CAT_DEFAULT
            const pct = Math.round((count / Math.max(categoryTotal, 1)) * 100)
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
      {chartData.length > 0 && (
        <div className="px-4 pt-3 pb-1">
          <CommentsChart
            data={chartData}
            segments={live.title_changes && live.title_changes.length > 1 ? live.title_changes : undefined}
          />
        </div>
      )}
    </div>
  )
}

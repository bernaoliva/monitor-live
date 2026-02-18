"use client"

import { useEffect, useState, useRef, useMemo } from "react"
import { useParams } from "next/navigation"
import Link from "next/link"
import { doc, collection, onSnapshot, query, orderBy, where, limit, updateDoc, increment } from "firebase/firestore"
import { db } from "@/lib/firebase"
import { Live, Comment, ChartPoint } from "@/lib/types"
import CommentFeed from "@/components/CommentFeed"
import CommentsChart from "@/components/CommentsChart"
import ExportButton from "@/components/ExportButton"
import { ArrowLeft, ExternalLink, Clock } from "lucide-react"
import { formatDistanceToNow, format } from "date-fns"
import { ptBR } from "date-fns/locale"

function buildChartData(comments: Comment[], dismissed: Set<string>): ChartPoint[] {
  const buckets: Record<string, { total: number; technical: number }> = {}
  comments.forEach((c) => {
    const minute = format(new Date(c.ts), "HH:mm")
    if (!buckets[minute]) buckets[minute] = { total: 0, technical: 0 }
    buckets[minute].total++
    if (c.is_technical && !dismissed.has(c.id)) buckets[minute].technical++
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

const CAT_BAR_COLOR: Record<string, string> = {
  AUDIO: "#60a5fa",
  VIDEO: "#c084fc",
  REDE:  "#fb923c",
  GC:    "#22d3ee",
}
const CAT_TEXT: Record<string, string> = {
  AUDIO: "text-blue-300",
  VIDEO: "text-purple-300",
  REDE:  "text-orange-300",
  GC:    "text-cyan-300",
}

export default function LivePage() {
  const { id }                    = useParams<{ id: string }>()
  const [live, setLive]           = useState<Live | null>(null)
  const [notFound, setNotFound]   = useState(false)
  const [comments, setComments]           = useState<Comment[]>([])
  const [chartComments, setChartComments] = useState<Comment[]>([])
  const [techComments, setTechComments]   = useState<Comment[]>([])
  const [filter, setFilter]           = useState<"all" | "technical">("technical")
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  const allComments               = useRef<Comment[]>([])

  // Carrega dismissed do localStorage (mesmo key que o LiveCard)
  useEffect(() => {
    try {
      const stored = localStorage.getItem(`dismissed_${id}`)
      if (stored) setDismissed(new Set(JSON.parse(stored)))
    } catch {}
  }, [id])

  const dismissComment = async (c: Comment) => {
    setDismissed(prev => {
      const next = new Set([...prev, c.id])
      try { localStorage.setItem(`dismissed_${id}`, JSON.stringify([...next])) } catch {}
      return next
    })
    try {
      await updateDoc(doc(db, "lives", id, "comments", c.id), {
        is_technical: false,
      })
      const liveUpdate: Record<string, unknown> = {
        technical_comments: increment(-1),
      }
      if (c.category && c.issue) {
        liveUpdate[`issue_counts.${c.category}:${c.issue}`] = increment(-1)
      }
      await updateDoc(doc(db, "lives", id), liveUpdate)
    } catch (e) {
      console.error("Erro ao descartar comentário:", e)
    }
  }

  useEffect(() => {
    const unsub1 = onSnapshot(doc(db, "lives", id), (snap) => {
      if (!snap.exists()) { setNotFound(true); setLive(null); return }
      setNotFound(false)
      const d = snap.data()
      setLive({
        video_id:           snap.id,
        channel:            d.channel            ?? "",
        title:              d.title              ?? snap.id,
        url:                d.url                ?? "",
        status:             d.status             ?? "ended",
        started_at:         d.started_at         ?? "",
        ended_at:           d.ended_at           ?? null,
        last_seen_at:       d.last_seen_at       ?? "",
        total_comments:     d.total_comments     ?? 0,
        technical_comments: d.technical_comments ?? 0,
        issue_counts:       d.issue_counts       ?? {},
      } satisfies Live)
    })

    // Últimas 3000 mensagens para o feed "TODOS" (mais recentes primeiro)
    const qFeed = query(
      collection(db, "lives", id, "comments"),
      orderBy("ts", "desc"),
      limit(3000)
    )
    const unsub2 = onSnapshot(qFeed, (snap) => {
      const data = snap.docs.map((d) => {
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
      allComments.current = data
      setComments(data)
    }, (err) => console.error("[Firestore] comments query error:", err))

    // Todos os comentários (sem limite) — apenas para o gráfico
    const qChart = query(
      collection(db, "lives", id, "comments"),
      orderBy("ts", "asc")
    )
    const unsub3 = onSnapshot(qChart, (snap) => {
      setChartComments(
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
    }, (err) => console.error("[Firestore] chartComments query error:", err))

    // Todos os comentários técnicos da transmissão inteira (sem limite)
    const qTech = query(
      collection(db, "lives", id, "comments"),
      where("is_technical", "==", true)
    )
    const unsub4 = onSnapshot(qTech, (snap) => {
      const data = snap.docs.map((d) => {
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
      }).sort((a, b) => a.ts.localeCompare(b.ts))
      setTechComments(data)
    }, (err) => console.error("[Firestore] techComments query error:", err))

    return () => { unsub1(); unsub2(); unsub3(); unsub4() }
  }, [id])

  // Feed "TODOS": com dismissed aplicado
  const activeComments = comments.map((c) =>
    dismissed.has(c.id) ? { ...c, is_technical: false } : c
  )
  // Feed "PROBLEMAS": todos os técnicos da transmissão, excluindo descartados
  const visibleTech = techComments.filter((c) => !dismissed.has(c.id))
  // Feed para exibição: mais recentes primeiro (comments já vem em desc do Firestore)
  const displayed = filter === "all"
    ? activeComments
    : [...visibleTech].sort((a, b) => b.ts.localeCompare(a.ts))
  const techCount   = visibleTech.length
  const chartData  = useMemo(() => buildChartData(chartComments, dismissed), [chartComments, dismissed])
  const techRate   = live
    ? Math.round((techCount / Math.max(live.total_comments, 1)) * 100)
    : 0

  // Problemas detectados: conta diretamente dos comentários técnicos visíveis
  const categoryBreakdown = useMemo(() => {
    const acc: Record<string, number> = {}
    visibleTech.forEach((c) => {
      const cat = normalizeCategory(c.category)
      if (cat) {
        acc[cat] = (acc[cat] || 0) + 1
      }
    })
    return Object.entries(acc)
      .filter(([, c]) => c > 0)
      .sort(([, a], [, b]) => b - a)
  }, [visibleTech])

  const catTotal = categoryBreakdown.reduce((s, [, c]) => s + c, 0)

  if (notFound) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center space-y-4 fade-up">
        <p className="font-data text-4xl text-white/10 font-bold">404</p>
        <p className="text-white/40 text-xs">Stream não encontrado</p>
        <Link href="/" className="text-[11px] text-emerald-400/60 hover:text-emerald-400 transition-colors font-mono">
          Voltar ao Painel
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-4 fade-up">
      {/* Navigation + Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1.5 min-w-0">
          <Link
            href="/"
            className="inline-flex items-center gap-1 text-white/35 hover:text-white/60 text-[11px] transition-colors font-mono"
          >
            <ArrowLeft size={11} />
            PAINEL
          </Link>
          <h1 className="text-[15px] font-bold text-white leading-tight max-w-2xl">
            {live?.title ?? id}
          </h1>
          <div className="flex items-center gap-2.5 flex-wrap">
            {live?.status === "active" ? (
              <span className="tag bg-emerald-500/15 text-emerald-400 border border-emerald-500/20">
                AO VIVO
              </span>
            ) : (
              <span className="tag bg-white/[0.04] text-white/35 border border-white/[0.06]">
                ENCERRADA
              </span>
            )}
            {live?.started_at && (
              <span className="flex items-center gap-1 text-[10px] text-white/35 font-mono">
                <Clock size={9} />
                {formatDistanceToNow(new Date(live.started_at), { locale: ptBR, addSuffix: true })}
              </span>
            )}
            {live?.url && (
              <a
                href={live.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-[10px] text-white/35 hover:text-white/55 transition-colors font-mono"
              >
                <ExternalLink size={9} /> YT
              </a>
            )}
          </div>
        </div>
        <ExportButton videoId={id} title={live?.title ?? id} comments={allComments} />
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
        <div className="stat-card stat-muted p-3">
          <p className="metric-label">Comentários</p>
          <p className="font-data text-xl font-bold text-white mt-0.5">
            {(live?.total_comments ?? 0).toLocaleString()}
          </p>
        </div>
        <div className="stat-card stat-red p-3">
          <p className="metric-label">Problemas</p>
          <p className="font-data text-xl font-bold text-red-400 mt-0.5">
            {techCount.toLocaleString()}
          </p>
        </div>
        <div className={`stat-card ${techRate > 15 ? "stat-red" : techRate > 5 ? "stat-blue" : "stat-green"} p-3`}>
          <p className="metric-label">Taxa</p>
          <p className={`font-data text-xl font-bold mt-0.5 ${
            techRate > 15 ? "text-red-400" : techRate > 5 ? "text-amber-400" : "text-emerald-400"
          }`}>{techRate}%</p>
        </div>
        <div className="stat-card stat-muted p-3">
          <p className="metric-label">Categorias</p>
          <p className="font-data text-xl font-bold text-white/60 mt-0.5">
            {categoryBreakdown.length}
          </p>
        </div>
      </div>

      {/* Chart + Problemas por categoria */}
      <div className="grid md:grid-cols-3 gap-2.5">
        <div className="md:col-span-2 panel p-4">
          <p className="metric-label mb-3">Volume por minuto</p>
          <CommentsChart data={chartData} />
        </div>

        <div className="panel p-4 space-y-3">
          <p className="metric-label">Problemas citados</p>
          {categoryBreakdown.length === 0 ? (
            <p className="text-white/30 text-[11px] font-mono">Nenhum problema</p>
          ) : (
            categoryBreakdown.map(([cat, count]) => {
              const pct      = Math.round((count / Math.max(catTotal, 1)) * 100)
              const barColor = CAT_BAR_COLOR[cat] ?? "rgba(255,255,255,0.2)"
              const textCls  = CAT_TEXT[cat] ?? "text-white/50"
              return (
                <div key={cat} className="space-y-1">
                  <div className="flex justify-between text-[10px]">
                    <span className={`font-bold font-mono uppercase ${textCls}`}>{cat}</span>
                    <span className={`font-data font-bold ${textCls}`}>{count}</span>
                  </div>
                  <div className="h-1 bg-white/[0.05] rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-700"
                      style={{ width: `${pct}%`, background: barColor }}
                    />
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>

      {/* Comment feed */}
      <div className="panel overflow-hidden">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/[0.06]">
          <div className="flex items-center gap-2.5">
            <p className="text-[10px] font-bold text-white/40 uppercase tracking-[0.12em] font-mono">
              Comentários
            </p>
            <span className="font-data text-[10px] text-white/30">{displayed.length}</span>
          </div>
          <div className="flex gap-0.5 bg-white/[0.03] p-0.5 rounded">
            <button
              onClick={() => setFilter("all")}
              className={`px-2.5 py-1 text-[10px] font-bold rounded transition-all font-mono tracking-wider ${
                filter === "all"
                  ? "bg-white/[0.08] text-white/70"
                  : "text-white/30 hover:text-white/50"
              }`}
            >
              últimas {activeComments.length} msgs
            </button>
            <button
              onClick={() => setFilter("technical")}
              className={`px-2.5 py-1 text-[10px] font-bold rounded transition-all font-mono tracking-wider ${
                filter === "technical"
                  ? "bg-red-500/15 text-red-400"
                  : "text-white/30 hover:text-white/50"
              }`}
            >
              PROBLEMAS ({techCount})
            </button>
          </div>
        </div>
        <CommentFeed comments={displayed} onDismiss={dismissComment} />
      </div>
    </div>
  )
}

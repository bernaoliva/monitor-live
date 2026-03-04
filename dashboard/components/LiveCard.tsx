"use client"

import { useEffect, useState, useMemo, useRef } from "react"
import Link from "next/link"
import Image from "next/image"
import {
  collection, onSnapshot, query, where,
  doc, updateDoc, increment,
} from "firebase/firestore"
import { db } from "@/lib/firebase"
import { Live, Comment, ChartPoint } from "@/lib/types"
import CommentsChart from "@/components/CommentsChart"
import { AlertTriangle, ArrowRight, X, Pin, Volume2, VolumeOff } from "lucide-react"
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

type CatStyle = { text: string; leftBar: string; bg: string; border: string; barColor: string }
const CAT_STYLE: Record<string, CatStyle> = {
  AUDIO: { text: "text-blue-300",   leftBar: "bg-blue-400/50",   bg: "bg-blue-500/10",   border: "border-blue-500/20",   barColor: "#60a5fa" },
  VIDEO: { text: "text-purple-300", leftBar: "bg-purple-400/50", bg: "bg-purple-500/10", border: "border-purple-500/20", barColor: "#c084fc" },
  REDE:  { text: "text-orange-300", leftBar: "bg-orange-400/50", bg: "bg-orange-500/10", border: "border-orange-500/20", barColor: "#fb923c" },
  GC:    { text: "text-cyan-300",   leftBar: "bg-cyan-400/50",   bg: "bg-cyan-500/10",   border: "border-cyan-500/20",   barColor: "#22d3ee" },
}
const CAT_DEFAULT: CatStyle = {
  text: "text-white/50", leftBar: "bg-white/15", bg: "bg-white/[0.04]", border: "border-white/[0.06]", barColor: "rgba(255,255,255,0.2)",
}

function formatViewers(v: number | null | undefined): string | null {
  if (v == null) return null
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}k`
  return v.toString()
}

export default function LiveCard({
  live,
  onDismiss,
  liveCount = 1,
  isPinned = false,
  onPin,
  isDragging = false,
  isDragOver = false,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
}: {
  live: Live
  onDismiss?: () => void
  liveCount?: number
  isPinned?: boolean
  onPin?: () => void
  isDragging?: boolean
  isDragOver?: boolean
  onDragStart?: (e: React.DragEvent) => void
  onDragOver?: (e: React.DragEvent) => void
  onDrop?: (e: React.DragEvent) => void
  onDragEnd?: (e: React.DragEvent) => void
}) {
  // Alturas calibradas para preencher 1080p
  // 1-3: 1 linha | 4-6: 2-3 cols, 2 linhas | 7-10: 4-5 cols, 2 linhas | 11-15: 3 linhas | 16+: 4 linhas
  const chartHeight  = liveCount === 1 ? 340 : liveCount === 2 ? 270 : liveCount <= 3 ? 210 : liveCount <= 6 ? 125 : liveCount <= 8 ? 120 : liveCount <= 10 ? 140 : liveCount <= 15 ? 90 : 60
  const commentsMaxH = liveCount === 1 ? 440 : liveCount === 2 ? 340 : liveCount <= 3 ? 260 : liveCount <= 6 ? 138 : liveCount <= 8 ? 135 : liveCount <= 10 ? 160 : liveCount <= 15 ? 110 : 70
  const showCats     = true
  const compactCats  = liveCount >= 4
  const denseHeader  = liveCount >= 7
  const ultraDense   = liveCount >= 10  // modo ultra-compacto

  const [chartData,       setChartData]       = useState<ChartPoint[]>([])
  const [allTechComments, setAllTechComments] = useState<Comment[]>([])
  const [dismissed,       setDismissed]       = useState<Set<string>>(new Set())
  const [alertKey,        setAlertKey]        = useState(0)
  const [dismissError,    setDismissError]    = useState(false)
  const [muted,           setMuted]           = useState(live.channel?.toUpperCase() !== "CAZETV")
  const techSnapshotReadyRef = useRef(false)
  const mutedRef = useRef(muted)
  mutedRef.current = muted
  const audioCtxRef = useRef<AudioContext | null>(null)

  const playAlertSound = () => {
    try {
      if (!audioCtxRef.current) audioCtxRef.current = new AudioContext()
      const ctx = audioCtxRef.current
      const now = ctx.currentTime

      // Alerta urgente: 3 pulsos duplos crescentes (~4s total)
      const pulses = [
        // pulso 1 — dois tons rápidos
        { start: 0,    freq: 880,  dur: 0.18, vol: 0.25 },
        { start: 0.22, freq: 1047, dur: 0.18, vol: 0.25 },
        // pulso 2
        { start: 1.2,  freq: 880,  dur: 0.18, vol: 0.30 },
        { start: 1.42, freq: 1047, dur: 0.18, vol: 0.30 },
        // pulso 3 — mais forte e longo
        { start: 2.4,  freq: 880,  dur: 0.22, vol: 0.35 },
        { start: 2.66, freq: 1047, dur: 0.30, vol: 0.35 },
      ]
      for (const p of pulses) {
        const osc = ctx.createOscillator()
        const gain = ctx.createGain()
        osc.type = "square"
        osc.frequency.value = p.freq
        gain.gain.setValueAtTime(p.vol, now + p.start)
        gain.gain.exponentialRampToValueAtTime(0.001, now + p.start + p.dur)
        osc.connect(gain).connect(ctx.destination)
        osc.start(now + p.start)
        osc.stop(now + p.start + p.dur + 0.05)
      }
    } catch {}
  }

  const minuteKeyFromTs = (ts: string): string | null => {
    const m = ts.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/)
    return m ? `${m[1]}T${m[2]}` : null
  }

  useEffect(() => {
    try {
      const stored = localStorage.getItem(`dismissed_${live.video_id}`)
      if (stored) setDismissed(new Set(JSON.parse(stored)))
    } catch {}
  }, [live.video_id])


  const dismissComment = async (c: Comment) => {
    const minuteKey = minuteKeyFromTs(c.ts)
    if (minuteKey) {
      setChartData((prev) =>
        prev.map((p) => p.minute === minuteKey ? { ...p, technical: Math.max(0, (p.technical ?? 0) - 1) } : p)
      )
    }
    setDismissed(prev => {
      const next = new Set([...prev, c.id])
      try { localStorage.setItem(`dismissed_${live.video_id}`, JSON.stringify([...next])) } catch {}
      return next
    })
    try {
      await updateDoc(doc(db, "lives", live.video_id, "comments", c.id), { is_technical: false })
      const liveUpdate: Record<string, unknown> = { technical_comments: increment(-1) }
      if (c.category && c.issue) {
        liveUpdate[`issue_counts.${c.category}:${c.issue}`] = increment(-1)
      }
      await updateDoc(doc(db, "lives", live.video_id), liveUpdate)
      if (minuteKey) {
        await updateDoc(doc(db, "lives", live.video_id, "minutes", minuteKey), { technical: increment(-1) })
      }
    } catch (e) {
      console.error("Erro ao descartar comentário:", e)
      setDismissError(true)
      setTimeout(() => setDismissError(false), 3000)
    }
  }

  useEffect(() => {
    const unsub = onSnapshot(
      query(collection(db, "lives", live.video_id, "minutes")),
      (snap) => {
        setChartData(
          snap.docs
            .filter((d) => /^\d{2}:\d{2}$|^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(d.id))
            .map((d) => {
              const raw = d.data()
              return { minute: d.id, total: raw.total ?? 0, technical: raw.technical ?? 0 } satisfies ChartPoint
            })
            .sort((a, b) => a.minute.localeCompare(b.minute))
        )
      }
    )
    return () => unsub()
  }, [live.video_id])

  useEffect(() => {
    techSnapshotReadyRef.current = false
    const unsub = onSnapshot(
      query(collection(db, "lives", live.video_id, "comments"), where("is_technical", "==", true)),
      (snap) => {
        const hasNew = techSnapshotReadyRef.current && snap.docChanges().some((ch) => ch.type === "added")
        setAllTechComments(
          snap.docs.map((d) => {
            const raw = d.data()
            return {
              id: d.id, author: raw.author ?? "", text: raw.text ?? "", ts: raw.ts ?? "",
              is_technical: raw.is_technical ?? false, category: raw.category ?? null,
              issue: raw.issue ?? null, severity: raw.severity ?? "none",
            } satisfies Comment
          })
        )
        if (hasNew) { setAlertKey((k) => k + 1); if (!mutedRef.current) playAlertSound() }
        techSnapshotReadyRef.current = true
      },
      (err) => console.error("[LiveCard] tech feed error:", err)
    )
    return () => unsub()
  }, [live.video_id])

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
      .map((p) => ({ ...p, technical: techByMinute[p.minute] ?? 0 }))
      .sort((a, b) => a.minute.localeCompare(b.minute))
  }, [chartData, visibleComments])

  const categoryBreakdown = useMemo(() => {
    const acc: Record<string, number> = {}
    visibleComments.forEach((c) => {
      const cat = normalizeCategory(c.category)
      if (cat) acc[cat] = (acc[cat] || 0) + 1
    })
    return Object.entries(acc).filter(([, c]) => c > 0).sort(([, a], [, b]) => b - a)
  }, [visibleComments])

  const categoryTotal = categoryBreakdown.reduce((s, [, c]) => s + c, 0)

  const techRate = Math.round((visibleComments.length / Math.max(live.total_comments, 1)) * 100)

  const lastCat     = visibleComments[0] ? normalizeCategory(visibleComments[0].category) : null
  const flashFill   = lastCat === "AUDIO" ? "rgba(96,165,250,0.55)"  : lastCat === "VIDEO" ? "rgba(192,132,252,0.55)"
    : lastCat === "REDE"  ? "rgba(251,146,60,0.55)"  : lastCat === "GC" ? "rgba(34,211,238,0.55)"  : "rgba(239,68,68,0.55)"
  const flashBorder = lastCat === "AUDIO" ? "rgba(96,165,250,0.9)"   : lastCat === "VIDEO" ? "rgba(192,132,252,0.9)"
    : lastCat === "REDE"  ? "rgba(251,146,60,0.9)"   : lastCat === "GC" ? "rgba(34,211,238,0.9)"   : "rgba(239,68,68,0.9)"

  const channelKey  = (live.channel || "").toUpperCase()
  const channelLogo = channelKey === "GETV" ? "/getv-logo.png" : channelKey === "CAZETV" ? "/cazetv-logo-branco.png" : null
  const logoW       = channelKey === "GETV" ? 120 : 150
  const logoH       = channelKey === "GETV" ? 36  : 46

  const channelBorderColor =
    techRate > 15 ? "rgba(239,68,68,0.65)" :
    techRate > 5  ? "rgba(245,158,11,0.55)" :
    channelKey === "GETV" ? "rgba(16,185,129,0.50)" :
    "rgba(255,255,255,0.25)"

  const channelGlow =
    techRate > 15 ? "0 0 12px rgba(239,68,68,0.30)" :
    techRate > 5  ? "0 0 12px rgba(245,158,11,0.25)" :
    channelKey === "GETV" ? "0 0 12px rgba(16,185,129,0.22)" :
    "0 0 8px rgba(255,255,255,0.08)"

  return (
    <div
      draggable={!!onDragStart}
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onDragEnd={onDragEnd}
      className={`panel overflow-hidden relative transition-opacity h-full flex flex-col ${isDragging ? "dragging" : ""} ${isDragOver ? "drag-over" : ""}`}
      style={{ borderColor: channelBorderColor, borderWidth: "2px", boxShadow: channelGlow }}
    >

      {/* Flash ao detectar novo problema */}
      {alertKey > 0 && (
        <div
          key={alertKey}
          className="absolute inset-0 z-10 alert-flash rounded-lg pointer-events-none"
          style={{
            background: `linear-gradient(180deg, ${flashFill} 0%, rgba(0,0,0,0) 60%)`,
            boxShadow: `inset 0 0 0 2px ${flashBorder}`,
          }}
        />
      )}

      {/* Header */}
      <div className={`flex items-center justify-between px-3 border-b border-white/[0.06] ${ultraDense ? "py-1" : "py-2"}`}>
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <div className="relative w-1.5 h-1.5 shrink-0">
            <div className="absolute inset-0 rounded-full bg-emerald-400 pulse-dot" />
            <div className="absolute inset-0 rounded-full bg-emerald-400" />
          </div>
          <div className="min-w-0 flex-1">
            <span
              className={`font-bold text-white leading-tight block ${ultraDense ? "text-[9px] line-clamp-1 min-h-[14px]" : denseHeader ? "text-[10px] line-clamp-1 min-h-[16px]" : "text-[12px] line-clamp-2 min-h-[30px]"}`}
            >
              {live.title || live.video_id}
            </span>
            <div className={`flex items-center gap-2 ${ultraDense ? "mt-0" : "mt-0.5"}`}>
              {live.url && (
                <a
                  href={live.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  title="Abrir no YouTube"
                  className="shrink-0 flex items-center gap-1 hover:opacity-70 transition-opacity text-red-500"
                >
                  <svg width={ultraDense ? 10 : denseHeader ? 12 : 15} height={ultraDense ? 7 : denseHeader ? 9 : 11} viewBox="0 0 24 17" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round">
                    <rect x="1" y="1" width="22" height="15" rx="4"/>
                    <path d="M10 5.5L16.5 8.5L10 11.5V5.5Z"/>
                  </svg>
                  {!ultraDense && <span className={`${denseHeader ? "text-[7px]" : "text-[8px]"} font-thin tracking-widest`}>YOUTUBE</span>}
                </a>
              )}
              {formatViewers(live.concurrent_viewers) && (
                <span className={`${ultraDense ? "text-[8px]" : denseHeader ? "text-[9px]" : "text-[11px]"} text-white/80 font-mono`}>
                  {formatViewers(live.concurrent_viewers)} esp.
                </span>
              )}
              <span className={`${ultraDense ? "text-[8px]" : denseHeader ? "text-[9px]" : "text-[11px]"} font-mono font-bold text-red-400/80`}>
                {visibleComments.length} prob.
              </span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-2">
          <Link
            href={`/live/${live.video_id}`}
            className="flex items-center gap-0.5 text-[9px] font-bold font-mono text-white/30 hover:text-white/60 transition-colors"
          >
            ABRIR <ArrowRight size={9} />
          </Link>
          <div className="flex flex-col items-center gap-1">
            <button
              onClick={() => setMuted((m) => !m)}
              title={muted ? "Ativar som" : "Silenciar"}
              className={`transition-colors ${muted ? "text-white/20 hover:text-white/50" : "text-emerald-400/80 hover:text-emerald-300"}`}
            >
              {muted ? <VolumeOff size={11} /> : <Volume2 size={11} />}
            </button>
            {onPin && (
              <button
                onClick={onPin}
                title={isPinned ? "Desafixar" : "Fixar no topo"}
                className={`transition-colors ${isPinned ? "text-amber-400/80 hover:text-amber-300" : "text-white/20 hover:text-white/50"}`}
              >
                <Pin size={11} />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Gráfico com logo do canal como marca d'água */}
      <div className={`relative px-3 pb-0 ${ultraDense ? "pt-1" : "pt-2"}`}>
        {channelLogo && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-0">
            <Image
              src={channelLogo}
              alt=""
              width={logoW}
              height={logoH}
              className="object-contain opacity-[0.05]"
            />
          </div>
        )}
        <div className="relative z-[1]">
          <CommentsChart data={chartDataDisplay} height={chartHeight} showLegend={false} />
        </div>
      </div>

      {/* Pills de categoria — só para 4-6 lives */}
      {showCats && compactCats && (
        <div className={`px-3 flex items-center gap-1.5 flex-wrap border-t border-white/[0.04] ${ultraDense ? "py-1 min-h-[22px]" : "py-1.5 min-h-[28px]"}`}>
          {categoryBreakdown.map(([cat, count]) => {
            const s = CAT_STYLE[cat] ?? CAT_DEFAULT
            return (
              <span key={cat} className={`text-[7px] font-bold font-mono px-1.5 py-0.5 rounded border ${s.bg} ${s.text} ${s.border}`}>
                {cat} {count}
              </span>
            )
          })}
        </div>
      )}

      {/* Comentários + barra lateral de categorias (1-3 lives) */}
      <div className="border-t border-white/[0.06] flex min-h-0 flex-1">

        {/* Feed de comentários */}
        <div className={`flex flex-col ${showCats && !compactCats ? "flex-[4] min-w-0 border-r border-white/[0.06]" : "flex-1 min-w-0"}`}>
          <div className="px-3 py-1.5 flex items-center gap-1.5 border-b border-white/[0.04] shrink-0">
            <AlertTriangle size={8} className="text-red-400/60 shrink-0" />
            <span className="text-[8px] font-bold font-mono uppercase tracking-wider text-white/40">Problemas recentes</span>
            <span className="font-data text-[9px] text-white/25 ml-auto">{visibleComments.length}</span>
          </div>
          {dismissError && (
            <div className="px-3 py-1 text-[9px] text-red-400/70 font-mono bg-red-500/5 border-b border-red-500/10 shrink-0">
              Erro ao descartar. Tente novamente.
            </div>
          )}
          <div className="overflow-y-auto comments-scroll flex-1" style={{ minHeight: commentsMaxH, maxHeight: commentsMaxH }}>
            {visibleComments.length === 0 ? (
              <div className="h-full px-3 py-3 text-[10px] text-white/20 font-mono flex items-center">
                Nenhum problema detectado
              </div>
            ) : (
              visibleComments.map((c) => {
                const catKey  = normalizeCategory(c.category) ?? ""
                const catStyle = CAT_STYLE[catKey] ?? CAT_DEFAULT
                return (
                  <div
                    key={c.id}
                    className={`relative group flex items-center gap-2 px-3 border-b border-white/[0.03] last:border-0 hover:bg-white/[0.02] transition-colors ${ultraDense ? "h-7" : "h-9"}`}
                  >
                    <div className={`absolute left-0 top-0 bottom-0 w-0.5 ${catStyle.leftBar}`} />
                    <span className={`block ${ultraDense ? "w-1 h-1" : "w-1.5 h-1.5"} rounded-full shrink-0 ${SEV_DOT[c.severity] ?? SEV_DOT.none}`} />
                    <div className="flex-1 min-w-0">
                      <span className={`${ultraDense ? "text-[11px]" : "text-sm"} text-white/70 line-clamp-2 leading-tight`}>{c.text} <span className={`${ultraDense ? "text-[8px]" : "text-[9px]"} text-white/30 font-mono`}>— {c.author}</span></span>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      {catKey && <span className={`${ultraDense ? "text-[8px]" : "text-[9px]"} font-bold font-mono ${catStyle.text}`}>{catKey}</span>}
                      <span className={`${ultraDense ? "text-[8px]" : "text-[10px]"} text-white/50 font-mono`}>{format(new Date(c.ts.replace(" ", "T")), "HH:mm:ss")}</span>
                    </div>
                    <button
                      onClick={() => dismissComment(c)}
                      className="opacity-0 group-hover:opacity-100 transition-opacity shrink-0 text-white/25 hover:text-red-400/70"
                    >
                      <X size={10} />
                    </button>
                  </div>
                )
              })
            )}
          </div>
        </div>

        {/* Sidebar de categorias — só para 1-3 lives */}
        {showCats && !compactCats && (
          <div className="flex-[1] min-w-0 px-3 py-2.5 space-y-3">
            <p className="text-[11px] font-bold uppercase tracking-wider text-white/35">Por categoria</p>
            {categoryBreakdown.length === 0 ? (
              <p className="text-[13px] text-white/20 font-mono">—</p>
            ) : (
              categoryBreakdown.map(([cat, count]) => {
                const style = CAT_STYLE[cat] ?? CAT_DEFAULT
                const pct   = Math.round((count / Math.max(categoryTotal, 1)) * 100)
                return (
                  <div key={cat} className="space-y-1">
                    <div className="flex items-center justify-between">
                      <span className={`text-[11px] font-bold font-mono uppercase ${style.text}`}>{cat}</span>
                      <span className={`font-data text-[13px] font-bold ${style.text}`}>{count}</span>
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
        )}

      </div>
    </div>
  )
}

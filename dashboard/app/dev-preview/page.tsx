"use client"

import { useState } from "react"
import Link from "next/link"
import Image from "next/image"
import { ArrowLeft, ArrowRight, AlertTriangle, X } from "lucide-react"

// ── Mock data ─────────────────────────────────────────────────────────────────

type MockComment = { id: string; text: string; ts: string; category: string; severity: string }
type MockLive    = { video_id: string; title: string; channel: string; total_comments: number; tech_count: number; viewers: number }

const MOCK_COMMENTS: MockComment[] = [
  { id: "1", text: "sem áudio na transmissão",    ts: "21:14", category: "AUDIO", severity: "high"   },
  { id: "2", text: "tela preta aqui também",       ts: "21:13", category: "VIDEO", severity: "high"   },
  { id: "3", text: "caiu de novo pra mim",         ts: "21:12", category: "REDE",  severity: "medium" },
  { id: "4", text: "placar sumiu do vídeo",        ts: "21:11", category: "GC",    severity: "low"    },
  { id: "5", text: "buffering constante aqui",     ts: "21:10", category: "REDE",  severity: "medium" },
  { id: "6", text: "travou aqui pra mim",          ts: "21:09", category: "VIDEO", severity: "low"    },
  { id: "7", text: "áudio voltou mas tá atrasado", ts: "21:08", category: "AUDIO", severity: "medium" },
]

const MOCK_CATS: Array<[string, number]> = [["AUDIO", 12], ["VIDEO", 8], ["REDE", 5], ["GC", 3]]
const CAT_TOTAL = 28

const MOCK_LIVES: MockLive[] = [
  { video_id: "m1", title: "CazeTV AO VIVO — Brasileirão: Flamengo x Palmeiras",     channel: "CAZETV", total_comments: 142800, tech_count: 28, viewers: 487000 },
  { video_id: "m2", title: "ge.tv AO VIVO — Libertadores: Boca Juniors x River",     channel: "GETV",   total_comments:  61200, tech_count:  6, viewers:  92000 },
  { video_id: "m3", title: "CazeTV AO VIVO — NBA: Lakers x Celtics",                 channel: "CAZETV", total_comments:  38400, tech_count: 12, viewers: 210000 },
  { video_id: "m4", title: "ge.tv AO VIVO — Copa do Brasil: Atlético x Corinthians", channel: "GETV",   total_comments:  22100, tech_count:  4, viewers:  74000 },
  { video_id: "m5", title: "CazeTV AO VIVO — F1: GP da Espanha",                     channel: "CAZETV", total_comments:  95600, tech_count: 19, viewers: 320000 },
  { video_id: "m6", title: "ge.tv AO VIVO — Vôlei: Brasil x França",                 channel: "GETV",   total_comments:  14300, tech_count:  2, viewers:  38000 },
  { video_id: "m7", title: "CazeTV AO VIVO — UFC 310: Main Card",                    channel: "CAZETV", total_comments: 204000, tech_count: 31, viewers: 512000 },
  { video_id: "m8", title: "ge.tv AO VIVO — Tênis: Roland Garros Semifinal",         channel: "GETV",   total_comments:   9800, tech_count:  1, viewers:  21000 },
  { video_id: "m9", title: "CazeTV AO VIVO — Boxe: Canelo x Bivol 2",                channel: "CAZETV", total_comments: 178000, tech_count: 24, viewers: 443000 },
  { video_id: "ma", title: "ge.tv AO VIVO — Copa do Mundo: Brasil x Argentina",      channel: "GETV",   total_comments: 312000, tech_count: 44, viewers: 890000 },
]

// ── Helpers ───────────────────────────────────────────────────────────────────

const SEV_DOT: Record<string, string> = { high: "bg-red-400", medium: "bg-amber-400", low: "bg-yellow-300" }
type CatStyle = { text: string; leftBar: string; bg: string; border: string; barColor: string }
const CAT_STYLE: Record<string, CatStyle> = {
  AUDIO: { text: "text-blue-300",   leftBar: "bg-blue-400/50",   bg: "bg-blue-500/10",   border: "border-blue-500/20",   barColor: "#60a5fa" },
  VIDEO: { text: "text-purple-300", leftBar: "bg-purple-400/50", bg: "bg-purple-500/10", border: "border-purple-500/20", barColor: "#c084fc" },
  REDE:  { text: "text-orange-300", leftBar: "bg-orange-400/50", bg: "bg-orange-500/10", border: "border-orange-500/20", barColor: "#fb923c" },
  GC:    { text: "text-cyan-300",   leftBar: "bg-cyan-400/50",   bg: "bg-cyan-500/10",   border: "border-cyan-500/20",   barColor: "#22d3ee" },
}
const CAT_DEFAULT: CatStyle = { text: "text-white/50", leftBar: "bg-white/15", bg: "bg-white/[0.04]", border: "border-white/[0.06]", barColor: "rgba(255,255,255,0.2)" }

const CHANNEL_LOGO: Record<string, { src: string; w: number; h: number }> = {
  CAZETV: { src: "/cazetv-logo-branco.png", w: 150, h: 46 },
  GETV:   { src: "/getv-logo.png",          w: 120, h: 36 },
}

function MockChart({ height }: { height: number }) {
  return (
    <div style={{ height }} className="relative">
      <svg viewBox="0 0 400 160" className="w-full h-full opacity-40" preserveAspectRatio="none">
        <defs>
          <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#3b82f6" stopOpacity="0.4"/>
            <stop offset="95%" stopColor="#3b82f6" stopOpacity="0"/>
          </linearGradient>
          <linearGradient id="g2" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#ef4444" stopOpacity="0.5"/>
            <stop offset="95%" stopColor="#ef4444" stopOpacity="0"/>
          </linearGradient>
        </defs>
        <path d="M0,140 C30,120 60,80 90,70 C120,60 150,95 180,80 C210,65 240,40 270,35 C300,30 330,50 360,42 C380,36 400,28 400,28 L400,160 L0,160 Z" fill="url(#g1)"/>
        <path d="M0,140 C30,120 60,80 90,70 C120,60 150,95 180,80 C210,65 240,40 270,35 C300,30 330,50 360,42 C380,36 400,28 400,28" fill="none" stroke="#3b82f6" strokeWidth="2"/>
        <path d="M0,155 C30,150 60,143 90,138 C120,133 150,147 180,141 C210,135 240,123 270,118 C300,113 330,126 360,120 C380,116 400,110 400,110 L400,160 L0,160 Z" fill="url(#g2)"/>
        <path d="M0,155 C30,150 60,143 90,138 C120,133 150,147 180,141 C210,135 240,123 270,118 C300,113 330,126 360,120 C380,116 400,110 400,110" fill="none" stroke="#ef4444" strokeWidth="2"/>
      </svg>
      <div className="absolute bottom-0 left-0 right-0 flex justify-between px-1">
        {["21:00","21:15","21:30","21:45","22:00","22:15"].map((t) => (
          <span key={t} className="text-[8px] text-white/15 font-mono">{t}</span>
        ))}
      </div>
    </div>
  )
}

function MockCard({ live, count }: { live: MockLive; count: number }) {
  const chartHeight  = count <= 3 ? 175 : 125
  const commentsMaxH = count <= 3 ? 190 : count <= 6 ? 138 : 150
  const showCats    = true
  const compactCats = count >= 4
  const techRate    = Math.round((live.tech_count / Math.max(live.total_comments, 1)) * 100)
  const denseHeader = count >= 9
  const channelKey  = live.channel.toUpperCase()
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

  const logo = CHANNEL_LOGO[channelKey]

  return (
    <div className="panel overflow-hidden relative" style={{ borderColor: channelBorderColor, borderWidth: "2px", boxShadow: channelGlow }}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-white/[0.06]">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <div className="relative w-1.5 h-1.5 shrink-0">
            <div className="absolute inset-0 rounded-full bg-emerald-400 pulse-dot" />
            <div className="absolute inset-0 rounded-full bg-emerald-400" />
          </div>
          <div className="min-w-0 flex-1">
            <span className={`font-bold text-white line-clamp-2 leading-tight block ${
              (count >= 9 && live.title.length > 38) || (count >= 7 && live.title.length > 52)
                ? "text-[11px]" : "text-[12px]"
            }`}>{live.title}</span>
            <div className="flex items-center gap-2 mt-0.5">
              <a href="#" title="Abrir no YouTube" className="shrink-0 flex items-center gap-1 hover:opacity-70 transition-opacity text-red-500">
                <svg width={denseHeader ? 12 : 15} height={denseHeader ? 9 : 11} viewBox="0 0 24 17" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round">
                  <rect x="1" y="1" width="22" height="15" rx="4"/>
                  <path d="M10 5.5L16.5 8.5L10 11.5V5.5Z"/>
                </svg>
                <span className={`${denseHeader ? "text-[7px]" : "text-[8px]"} font-thin tracking-widest`}>YOUTUBE</span>
              </a>
              <span className={`${denseHeader ? "text-[9px]" : "text-[11px]"} text-white/80 font-mono`}>
                {live.viewers >= 1_000_000 ? `${(live.viewers/1_000_000).toFixed(1)}M` : live.viewers >= 1_000 ? `${(live.viewers/1_000).toFixed(0)}k` : live.viewers} esp.
              </span>
              <span className={`${denseHeader ? "text-[9px]" : "text-[11px]"} font-mono font-bold text-red-400/80`}>
                {live.tech_count} problemas
              </span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-2">
          <span className="flex items-center gap-0.5 text-[9px] font-bold font-mono text-white/30">ABRIR <ArrowRight size={9} /></span>
          <button className="text-white/20"><X size={11} /></button>
        </div>
      </div>

      {/* Gráfico + logo watermark */}
      <div className="relative px-3 pt-2 pb-0">
        {logo && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-0">
            <Image src={logo.src} alt="" width={logo.w} height={logo.h} className="object-contain opacity-[0.05]" />
          </div>
        )}
        <div className="relative z-[1]">
          <MockChart height={chartHeight} />
        </div>
      </div>

      {/* Pills de categoria — 4-6 lives */}
      {showCats && compactCats && (
        <div className="px-3 py-1.5 flex items-center gap-1.5 flex-wrap border-t border-white/[0.04]">
          {MOCK_CATS.map(([cat, count]) => {
            const s = CAT_STYLE[cat] ?? CAT_DEFAULT
            return (
              <span key={cat} className={`text-[7px] font-bold font-mono px-1.5 py-0.5 rounded border ${s.bg} ${s.text} ${s.border}`}>
                {cat} {count}
              </span>
            )
          })}
        </div>
      )}

      {/* Comentários + sidebar de categorias */}
      <div className="border-t border-white/[0.06] flex min-h-0">
        <div className={showCats && !compactCats ? "flex-[4] min-w-0 border-r border-white/[0.06]" : "flex-1 min-w-0"}>
          <div className="px-3 py-1.5 flex items-center gap-1.5 border-b border-white/[0.04]">
            <AlertTriangle size={8} className="text-red-400/60 shrink-0" />
            <span className="text-[8px] font-bold font-mono uppercase tracking-wider text-white/40">Problemas recentes</span>
            <span className="font-data text-[9px] text-white/25 ml-auto">{live.tech_count}</span>
          </div>
          <div className="overflow-y-auto comments-scroll" style={{ maxHeight: commentsMaxH }}>
            {MOCK_COMMENTS.map((c) => {
              const s = CAT_STYLE[c.category] ?? CAT_DEFAULT
              return (
                <div key={c.id} className="relative group flex items-start gap-2 px-3 py-1.5 border-b border-white/[0.03] last:border-0">
                  <div className={`absolute left-0 top-0 bottom-0 w-0.5 ${s.leftBar}`} />
                  <span className={`block w-1 h-1 rounded-full shrink-0 mt-1.5 ${SEV_DOT[c.severity] ?? "bg-white/20"}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span className={`text-[7px] font-bold font-mono shrink-0 ${s.text}`}>{c.category}</span>
                      <span className="text-[9px] text-white/70 font-mono font-bold shrink-0 ml-auto">{c.ts}:00</span>
                    </div>
                    <span className="text-[11px] text-white/65 break-words leading-tight block">{c.text}</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Sidebar de categorias — 1-3 lives */}
        {showCats && !compactCats && (
          <div className="flex-[1] min-w-0 px-3 py-2.5 space-y-2">
            <p className="text-[7px] font-bold uppercase tracking-wider text-white/35">Por categoria</p>
            {MOCK_CATS.map(([cat, count]) => {
              const s   = CAT_STYLE[cat] ?? CAT_DEFAULT
              const pct = Math.round((count / CAT_TOTAL) * 100)
              return (
                <div key={cat} className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className={`text-[7px] font-bold font-mono uppercase ${s.text}`}>{cat}</span>
                    <span className={`font-data text-[9px] font-bold ${s.text}`}>{count}</span>
                  </div>
                  <div className="h-1 bg-white/[0.06] rounded-full overflow-hidden">
                    <div className="h-full rounded-full transition-all duration-700" style={{ width: `${pct}%`, background: s.barColor }} />
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Preview Page ──────────────────────────────────────────────────────────────

const COUNTS = [1, 2, 3, 4, 5, 6, 8, 10]

export default function DevPreviewPage() {
  const [count, setCount] = useState(2)
  const lives = MOCK_LIVES.slice(0, count)

  const gridCols =
    count <= 1 ? "" :
    count === 2 ? "grid grid-cols-2 gap-4" :
    count === 3 ? "grid grid-cols-3 gap-3" :
    count === 4 ? "grid grid-cols-2 gap-3" :
    count <= 6  ? "grid grid-cols-3 gap-2" :
    count <= 8  ? "grid grid-cols-4 gap-2" :
    "grid grid-cols-5 gap-2"

  const modeLabel =
    count <= 3 ? "categorias laterais + gráfico 175px" :
    count <= 6 ? "pills de categoria + gráfico 125px" :
    "sem categorias + gráfico 125px"

  return (
    <div className="space-y-4 fade-up">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <Link href="/" className="text-white/30 hover:text-white/60 transition-colors"><ArrowLeft size={14} /></Link>
          <h1 className="text-sm font-bold text-white">Simulação de Layout</h1>
          <span className="text-[10px] text-white/20 font-mono">{modeLabel}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-white/30 font-mono">lives:</span>
          <div className="flex gap-1">
            {COUNTS.map((n) => (
              <button
                key={n}
                onClick={() => setCount(n)}
                className={`w-7 h-7 rounded text-[11px] font-bold font-mono transition-all ${
                  count === n ? "bg-white/15 text-white" : "bg-white/[0.04] text-white/35 hover:bg-white/[0.08] hover:text-white/60"
                }`}
              >
                {n}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Grid */}
      <div className={gridCols}>
        {lives.map((live) => (
          <MockCard key={live.video_id} live={live} count={count} />
        ))}
      </div>
    </div>
  )
}

"use client"

import { useEffect, useState, useMemo } from "react"
import { collection, onSnapshot } from "firebase/firestore"
import { db } from "@/lib/firebase"
import { Live } from "@/lib/types"
import HistoricoCard from "@/components/HistoricoCard"
import { History } from "lucide-react"
import { format, parseISO } from "date-fns"
import { ptBR } from "date-fns/locale"
import { parseCompetition } from "@/lib/title-parser"
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts"

// ── Categoria de problema ──────────────────────────────────────────────────
function normCat(raw: string): string {
  const u = raw.toUpperCase().trim()
  if (/AUDIO|ÁUDIO|SOM\b|NARR/.test(u))              return "AUDIO"
  if (/VIDEO|VÍDEO|TELA|PIXEL|IMAG|CONGEL/.test(u))  return "VIDEO"
  if (/REDE|PLATAFORMA|BUFFER|CAIU|PLAT/.test(u))    return "REDE"
  if (/\bGC\b|PLACAR/.test(u))                       return "GC"
  return "OUTROS"
}

const CAT_COLOR: Record<string, string> = {
  AUDIO:  "#60a5fa",
  VIDEO:  "#c084fc",
  REDE:   "#fb923c",
  GC:     "#22d3ee",
  OUTROS: "rgba(255,255,255,0.18)",
}

// ── Tooltip do pie ─────────────────────────────────────────────────────────
interface PieTooltipProps {
  active?: boolean
  payload?: { name: string; value: number }[]
}
const PieTooltip = ({ active, payload }: PieTooltipProps) => {
  if (!active || !payload?.length) return null
  const d = payload[0]
  return (
    <div className="bg-[#1a1a24] border border-white/10 rounded-lg px-3 py-2 text-xs shadow-xl">
      <span className="font-bold text-white">{d.name}</span>
      <span className="text-white/50 ml-2">{d.value.toLocaleString("pt-BR")} ocorrências</span>
    </div>
  )
}

// ── Tipos ──────────────────────────────────────────────────────────────────
type ChannelFilter = "all" | "cazetv" | "getv"

// ── Página ─────────────────────────────────────────────────────────────────
export default function HistoricoPage() {
  const [lives, setLives] = useState<Live[]>([])
  const [channel, setChannel] = useState<ChannelFilter>("all")

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

  // Só lives com competição identificada, filtradas por canal
  const filtered = useMemo(() => {
    return lives.filter((l) => {
      if (channel !== "all" && l.channel.toLowerCase() !== channel) return false
      return parseCompetition(l.title) !== "OUTROS"
    })
  }, [lives, channel])

  // Dados do gráfico de pizza — agrega issue_counts de todas as lives filtradas
  const pieData = useMemo(() => {
    const acc: Record<string, number> = {}
    filtered.forEach((live) => {
      Object.entries(live.issue_counts || {}).forEach(([k, v]) => {
        const cat = normCat(k)
        acc[cat] = (acc[cat] || 0) + (v as number)
      })
    })
    return Object.entries(acc)
      .filter(([, v]) => v > 0)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
  }, [filtered])

  // Agrupamento por data
  const dateGroups = useMemo(() => {
    const acc: Record<string, Live[]> = {}
    filtered.forEach((live) => {
      const dateStr = (live.ended_at ?? live.started_at ?? "").slice(0, 10)
      if (!acc[dateStr]) acc[dateStr] = []
      acc[dateStr].push(live)
    })
    return Object.entries(acc)
      .sort(([a], [b]) => b.localeCompare(a))
      .map(([date, groupLives]) => ({ date, groupLives }))
  }, [filtered])

  // Stats
  const stats = useMemo(() => ({
    count:    filtered.length,
    msgs:     filtered.reduce((s, l) => s + l.total_comments, 0),
    problems: filtered.reduce((s, l) => s + l.technical_comments, 0),
  }), [filtered])

  function formatDateGroup(dateStr: string): string {
    if (!dateStr) return "—"
    try {
      return format(parseISO(dateStr), "dd MMM yyyy", { locale: ptBR }).toUpperCase()
    } catch {
      return dateStr
    }
  }

  return (
    <div className="space-y-5">
      {/* Header + canal filter */}
      <div className="fade-up flex items-center justify-between">
        <div className="flex items-center gap-3">
          <History size={16} className="text-white/20" />
          <div>
            <h1 className="text-sm font-bold text-white">Historico</h1>
            <p className="text-[11px] text-white/20 font-mono">
              {filtered.length > 0
                ? `${filtered.length} de ${lives.filter(l => parseCompetition(l.title) !== "OUTROS").length} transmiss${filtered.length > 1 ? "oes" : "ao"} com competicao`
                : "Nenhuma transmissao"}
            </p>
          </div>
        </div>

        <select
          value={channel}
          onChange={(e) => setChannel(e.target.value as ChannelFilter)}
          className="bg-[#12121a] border border-white/[0.08] text-white/50 text-[10px] font-mono rounded-md px-2.5 py-1.5 outline-none focus:border-white/20 cursor-pointer"
        >
          <option value="all">Todos os canais</option>
          <option value="cazetv">CazéTV</option>
          <option value="getv">GETV</option>
        </select>
      </div>

      {filtered.length > 0 && (
        <>
          {/* Stats strip */}
          <div className="fade-d1 grid grid-cols-3 panel overflow-hidden">
            <div className="px-4 py-3">
              <p className="text-[8px] font-bold uppercase tracking-wider text-white/40 mb-1">Lives</p>
              <p className="font-data text-base font-black text-white">{stats.count}</p>
            </div>
            <div className="px-4 py-3 border-l border-white/[0.06]">
              <p className="text-[8px] font-bold uppercase tracking-wider text-white/40 mb-1">Msgs</p>
              <p className="font-data text-base font-black text-white">
                {stats.msgs.toLocaleString("pt-BR")}
              </p>
            </div>
            <div className="px-4 py-3 border-l border-white/[0.06]">
              <p className="text-[8px] font-bold uppercase tracking-wider text-white/40 mb-1">Problemas</p>
              <p className={`font-data text-base font-black ${stats.problems > 0 ? "text-red-400" : "text-emerald-400"}`}>
                {stats.problems.toLocaleString("pt-BR")}
              </p>
            </div>
          </div>

          {/* Pie chart — categorias de problemas */}
          {pieData.length > 0 && (
            <div className="fade-d2 panel p-4">
              <p className="text-[8px] font-bold uppercase tracking-wider text-white/30 mb-3">
                Categorias de problemas
              </p>
              <div className="flex items-center gap-6">
                <div className="shrink-0" style={{ width: 120, height: 120 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={pieData}
                        dataKey="value"
                        cx="50%"
                        cy="50%"
                        innerRadius={30}
                        outerRadius={52}
                        paddingAngle={2}
                        isAnimationActive={false}
                      >
                        {pieData.map((entry) => (
                          <Cell
                            key={entry.name}
                            fill={CAT_COLOR[entry.name] ?? CAT_COLOR.OUTROS}
                          />
                        ))}
                      </Pie>
                      <Tooltip content={<PieTooltip />} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>

                <div className="flex-1 space-y-2">
                  {pieData.map(({ name, value }) => {
                    const total = pieData.reduce((s, d) => s + d.value, 0)
                    const pct   = Math.round((value / total) * 100)
                    const color = CAT_COLOR[name] ?? CAT_COLOR.OUTROS
                    return (
                      <div key={name} className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
                        <span className="text-[10px] font-mono text-white/40 flex-1 uppercase">{name}</span>
                        <span className="text-[10px] font-mono text-white/25">{pct}%</span>
                        <span className="text-[11px] font-data font-bold w-12 text-right" style={{ color }}>
                          {value.toLocaleString("pt-BR")}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          )}

          {/* Date groups */}
          <div className="fade-d3 space-y-6">
            {dateGroups.map(({ date, groupLives }) => (
              <div key={date} className="space-y-4">
                <div className="flex items-center gap-3">
                  <span className="text-[10px] font-bold font-mono text-white/25 shrink-0">
                    {formatDateGroup(date)}
                  </span>
                  <div className="flex-1 h-px bg-white/[0.06]" />
                  <span className="text-[10px] font-mono text-white/15 shrink-0">
                    {groupLives.length}
                  </span>
                </div>
                {groupLives.map((live) => (
                  <HistoricoCard key={live.video_id} live={live} />
                ))}
              </div>
            ))}
          </div>
        </>
      )}

      {filtered.length === 0 && lives.length > 0 && (
        <div className="fade-d1 panel flex flex-col items-center justify-center py-12 text-center">
          <p className="text-white/25 text-xs font-medium">Nenhuma transmissão com competição identificada</p>
          <p className="text-white/15 text-[11px] mt-1 font-mono">
            {channel !== "all" ? "Tente outro canal" : "Aguarde novas lives"}
          </p>
        </div>
      )}

      {lives.length === 0 && (
        <div className="fade-d1 panel flex flex-col items-center justify-center py-16 text-center">
          <History size={32} className="text-white/6 mb-3" />
          <p className="text-white/25 text-xs font-medium">Nenhuma transmissao encerrada</p>
          <p className="text-white/12 text-[11px] mt-1 font-mono">Lives encerradas aparecerao aqui</p>
        </div>
      )}
    </div>
  )
}

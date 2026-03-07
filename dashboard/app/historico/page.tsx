"use client"

import { useEffect, useState, useMemo } from "react"
import { collection, onSnapshot } from "firebase/firestore"
import { db } from "@/lib/firebase"
import { Live } from "@/lib/types"
import HistoricoCard from "@/components/HistoricoCard"
import { History, X } from "lucide-react"
import { format, parseISO } from "date-fns"
import { ptBR } from "date-fns/locale"
import { parseCompetition } from "@/lib/title-parser"
import {
  BarChart, Bar, XAxis, YAxis, Cell, Tooltip,
  ResponsiveContainer,
} from "recharts"

interface CompStat {
  name: string
  lives: number
  problems: number
}

interface ChartTooltipProps {
  active?: boolean
  payload?: { payload: CompStat }[]
}

const ChartTooltip = ({ active, payload }: ChartTooltipProps) => {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="bg-[#1a1a24] border border-white/10 rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="font-bold text-white mb-1">{d.name}</p>
      <p className="text-white/50">{d.lives} live{d.lives > 1 ? "s" : ""} · {d.problems} problemas</p>
    </div>
  )
}

export default function HistoricoPage() {
  const [lives, setLives] = useState<Live[]>([])
  const [selectedCompetitions, setSelectedCompetitions] = useState<Set<string>>(new Set())

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

  const compStats = useMemo((): CompStat[] => {
    const acc: Record<string, CompStat> = {}
    lives.forEach((live) => {
      const comp = parseCompetition(live.title)
      if (!acc[comp]) acc[comp] = { name: comp, lives: 0, problems: 0 }
      acc[comp].lives++
      acc[comp].problems += live.technical_comments
    })
    return Object.values(acc)
      .filter((c) => c.lives >= 2)
      .sort((a, b) => {
        if (a.name === "OUTROS") return 1
        if (b.name === "OUTROS") return -1
        return b.problems - a.problems
      })
  }, [lives])

  const filteredLives = useMemo(() => {
    if (selectedCompetitions.size === 0) return lives
    return lives.filter((l) => selectedCompetitions.has(parseCompetition(l.title)))
  }, [lives, selectedCompetitions])

  const dateGroups = useMemo(() => {
    const acc: Record<string, Live[]> = {}
    filteredLives.forEach((live) => {
      const dateStr = (live.ended_at ?? live.started_at ?? "").slice(0, 10)
      if (!acc[dateStr]) acc[dateStr] = []
      acc[dateStr].push(live)
    })
    return Object.entries(acc)
      .sort(([a], [b]) => b.localeCompare(a))
      .map(([date, groupLives]) => ({ date, groupLives }))
  }, [filteredLives])

  const summaryStats = useMemo(() => ({
    count:    filteredLives.length,
    msgs:     filteredLives.reduce((s, l) => s + l.total_comments, 0),
    problems: filteredLives.reduce((s, l) => s + l.technical_comments, 0),
  }), [filteredLives])

  function toggleCompetition(name: string) {
    setSelectedCompetitions((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  function formatDateGroup(dateStr: string): string {
    if (!dateStr) return "—"
    try {
      return format(parseISO(dateStr), "dd MMM yyyy", { locale: ptBR }).toUpperCase()
    } catch {
      return dateStr
    }
  }

  const chartHeight = Math.max(compStats.length * 26 + 16, 60)

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="fade-up flex items-center justify-between">
        <div className="flex items-center gap-3">
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
        {selectedCompetitions.size > 0 && (
          <button
            onClick={() => setSelectedCompetitions(new Set())}
            className="flex items-center gap-1.5 text-[10px] font-mono text-white/30 hover:text-white/60 transition-colors"
          >
            <X size={10} />
            LIMPAR FILTRO
          </button>
        )}
      </div>

      {lives.length > 0 && (
        <>
          {/* Interactive competition chart */}
          {compStats.length > 0 && (
            <div className="fade-d1 panel overflow-hidden px-2 pt-3 pb-2">
              <p className="text-[8px] font-bold uppercase tracking-wider text-white/30 mb-2 px-2">
                {selectedCompetitions.size > 0
                  ? `${selectedCompetitions.size} selecionada${selectedCompetitions.size > 1 ? "s" : ""} — clique para alternar`
                  : "Clique para filtrar por competição"}
              </p>
              <ResponsiveContainer width="100%" height={chartHeight}>
                <BarChart
                  data={compStats}
                  layout="vertical"
                  margin={{ top: 0, right: 44, left: 0, bottom: 0 }}
                  barCategoryGap={3}
                >
                  <XAxis type="number" hide />
                  <YAxis
                    dataKey="name"
                    type="category"
                    width={168}
                    tick={{ fill: "rgba(255,255,255,0.35)", fontSize: 10, fontFamily: "JetBrains Mono" }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v: string) => v.length > 22 ? v.slice(0, 20) + "…" : v}
                  />
                  <Tooltip
                    content={<ChartTooltip />}
                    cursor={{ fill: "rgba(255,255,255,0.03)" }}
                  />
                  <Bar
                    dataKey="problems"
                    radius={[0, 3, 3, 0]}
                    style={{ cursor: "pointer" }}
                    onClick={(data: CompStat) => toggleCompetition(data.name)}
                    label={{
                      position: "right",
                      fill: "rgba(255,255,255,0.25)",
                      fontSize: 10,
                      fontFamily: "JetBrains Mono",
                      formatter: (v: number) => v > 0 ? v : "",
                    }}
                  >
                    {compStats.map((entry) => (
                      <Cell
                        key={entry.name}
                        fill={
                          selectedCompetitions.has(entry.name)
                            ? "#ef4444"
                            : "rgba(255,255,255,0.09)"
                        }
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Summary stats */}
          <div className="fade-d2 grid grid-cols-3 panel overflow-hidden">
            <div className="px-4 py-3">
              <p className="text-[8px] font-bold uppercase tracking-wider text-white/40 mb-1">Lives</p>
              <p className="font-data text-base font-black text-white">{summaryStats.count}</p>
            </div>
            <div className="px-4 py-3 border-l border-white/[0.06]">
              <p className="text-[8px] font-bold uppercase tracking-wider text-white/40 mb-1">Msgs</p>
              <p className="font-data text-base font-black text-white">
                {summaryStats.msgs.toLocaleString("pt-BR")}
              </p>
            </div>
            <div className="px-4 py-3 border-l border-white/[0.06]">
              <p className="text-[8px] font-bold uppercase tracking-wider text-white/40 mb-1">Problemas</p>
              <p className={`font-data text-base font-black ${summaryStats.problems > 0 ? "text-red-400" : "text-emerald-400"}`}>
                {summaryStats.problems.toLocaleString("pt-BR")}
              </p>
            </div>
          </div>

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

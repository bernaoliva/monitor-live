"use client"

import { useMemo, useId } from "react"
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend, ReferenceLine,
} from "recharts"
import { ChartPoint, TitleChange } from "@/lib/types"
import { parseCompetition } from "@/lib/title-parser"

interface TooltipPayloadEntry {
  dataKey: string
  name: string
  value: number
  color: string
}

interface CustomTooltipProps {
  active?: boolean
  payload?: TooltipPayloadEntry[]
  label?: string
}

const CustomTooltip = ({ active, payload, label }: CustomTooltipProps) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-[#1a1a24] border border-white/10 rounded-xl p-3 text-xs shadow-xl">
      <p className="text-white/50 mb-2 font-mono">{String(label).slice(-5)}</p>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span className="text-white/60">{p.name}:</span>
          <span className="font-bold text-white">{p.value}</span>
        </div>
      ))}
    </div>
  )
}

function makeTechDot(clickable: boolean) {
  // eslint-disable-next-line react/display-name
  return (props: Record<string, unknown>) => {
    const { cx, cy, payload } = props as { cx: number; cy: number; payload: ChartPoint }
    if (!payload || payload.technical === 0) return <g />
    return (
      <circle
        cx={cx} cy={cy} r={clickable ? 5 : 3.5}
        fill="#ef4444" fillOpacity={0.85}
        stroke="#fff" strokeWidth={1} strokeOpacity={0.3}
        style={clickable ? { cursor: "pointer" } : undefined}
      />
    )
  }
}

export default function CommentsChart({ data, height = 220, showLegend = true, showXAxis = true, onMinuteClick, segments }: { data: ChartPoint[]; height?: number; showLegend?: boolean; showXAxis?: boolean; onMinuteClick?: (minute: string) => void; segments?: TitleChange[] }) {
  // IDs únicos por instância do chart para evitar conflitos SVG entre cards
  const uid = useId()
  const gradTotalId = `gradTotal-${uid}`
  const gradTechId  = `gradTech-${uid}`


  if (data.length === 0) {
    return (
      <div style={{ height }} className="flex items-center justify-center text-white/20 text-sm">
        Aguardando comentários...
      </div>
    )
  }

  const tickInterval = Math.max(1, Math.ceil(data.length / 8))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart
        data={data}
        margin={{ top: 4, right: 0, left: 8, bottom: showLegend ? 24 : showXAxis ? 6 : 2 }}
        style={onMinuteClick ? { cursor: "pointer" } : undefined}
        onClick={onMinuteClick ? (e) => {
          if (e?.activeLabel) onMinuteClick(e.activeLabel as string)
        } : undefined}
      >
        <defs>
          <linearGradient id={gradTotalId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
          </linearGradient>
          <linearGradient id={gradTechId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#ef4444" stopOpacity={0.4} />
            <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
        <XAxis
          dataKey="minute"
          hide={!showXAxis}
          tick={{ fill: "rgba(255,255,255,0.25)", fontSize: 8, fontFamily: "JetBrains Mono" }}
          tickLine={false}
          axisLine={false}
          interval={tickInterval}
          angle={40}
          textAnchor="start"
          dy={4}
          tickFormatter={(val: string) => val.slice(-5)}
        />
        <YAxis
          orientation="right"
          width={28}
          tick={{ fill: "rgba(255,255,255,0.25)", fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          allowDecimals={false}
        />
        <Tooltip content={<CustomTooltip />} />
        {showLegend && (
          <Legend wrapperStyle={{ paddingTop: 16, fontSize: 12, color: "rgba(255,255,255,0.4)" }} />
        )}
        <Area
          type="monotone"
          dataKey="total"
          name="Total"
          stroke="#3b82f6"
          strokeWidth={2}
          fill={`url(#${gradTotalId})`}
          dot={false}
          isAnimationActive={false}
        />
        <Area
          type="monotone"
          dataKey="technical"
          name="Técnicos"
          stroke="#ef4444"
          strokeWidth={2}
          fill={`url(#${gradTechId})`}
          dot={makeTechDot(!!onMinuteClick)}
          isAnimationActive={false}
        />
        {segments?.slice(1).map((seg, i) => {
          const label = parseCompetition(seg.title)
          const ts16 = seg.ts.slice(0, 16)
          // Snap ao minuto mais próximo disponível no chartData —
          // a troca pode ter ocorrido num minuto sem comentários (sem entry na subcoleção)
          const snap = data.find((d) => d.minute >= ts16)?.minute ?? data[data.length - 1]?.minute
          if (!snap) return null
          return (
            <ReferenceLine
              key={i}
              x={snap}
              stroke="rgba(255,255,255,0.18)"
              strokeDasharray="4 3"
              label={label !== "OUTROS" ? {
                value: label,
                position: "insideTopRight",
                fill: "rgba(255,255,255,0.30)",
                fontSize: 9,
                fontFamily: "JetBrains Mono",
              } : undefined}
            />
          )
        })}
      </AreaChart>
    </ResponsiveContainer>
  )
}

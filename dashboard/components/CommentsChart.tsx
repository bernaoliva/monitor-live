"use client"

import { useMemo, useId } from "react"
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from "recharts"
import { ChartPoint } from "@/lib/types"

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
      <p className="text-white/50 mb-2 font-mono">{label}</p>
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

function TechDot(props: Record<string, unknown>) {
  const { cx, cy, payload } = props as { cx: number; cy: number; payload: ChartPoint }
  if (!payload || payload.technical === 0) return null
  return <circle cx={cx} cy={cy} r={3.5} fill="#ef4444" fillOpacity={0.85} stroke="#fff" strokeWidth={1} strokeOpacity={0.3} />
}

export default function CommentsChart({ data, height = 220, showLegend = true }: { data: ChartPoint[]; height?: number; showLegend?: boolean }) {
  // IDs únicos por instância do chart para evitar conflitos SVG entre cards
  const uid = useId()
  const gradTotalId = `gradTotal-${uid}`
  const gradTechId  = `gradTech-${uid}`


  if (data.length === 0) {
    return (
      <div className="h-48 flex items-center justify-center text-white/20 text-sm">
        Aguardando comentários...
      </div>
    )
  }

  const tickInterval = Math.max(1, Math.ceil(data.length / 8))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 8, left: -20, bottom: showLegend ? 28 : 12 }}>
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
          tick={{ fill: "rgba(255,255,255,0.25)", fontSize: 10, fontFamily: "JetBrains Mono" }}
          tickLine={false}
          axisLine={false}
          interval={tickInterval}
          angle={-40}
          textAnchor="end"
          dy={4}
        />
        <YAxis
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
          dot={<TechDot />}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

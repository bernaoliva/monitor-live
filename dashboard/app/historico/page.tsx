"use client"

import { useEffect, useState, useMemo, useRef } from "react"
import { collection, onSnapshot, getDocs, query, where } from "firebase/firestore"
import { db } from "@/lib/firebase"
import { Live, TitleChange } from "@/lib/types"
import HistoricoCard from "@/components/HistoricoCard"
import { History } from "lucide-react"
import { format, parseISO } from "date-fns"
import { ptBR } from "date-fns/locale"
import { parseCompetition } from "@/lib/title-parser"
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts"

// ── Normalização de categorias (igual ao HistoricoCard) ───────────────────
function normCat(raw: string | null | undefined): string | null {
  if (!raw) return null
  const u = raw.toUpperCase().trim()
  if (/AUDIO|ÁUDIO|SOM\b|NARR/.test(u))              return "AUDIO"
  if (/VIDEO|VÍDEO|TELA|PIXEL|IMAG|CONGEL/.test(u))  return "VIDEO"
  if (/REDE|PLATAFORMA|BUFFER|CAIU|PLAT/.test(u))    return "REDE"
  if (/\bGC\b|PLACAR/.test(u))                       return "GC"
  return null
}

const CAT_COLOR: Record<string, string> = {
  AUDIO: "#60a5fa",
  VIDEO: "#c084fc",
  REDE:  "#fb923c",
  GC:    "#22d3ee",
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
      <span className="text-white/50 ml-2">{d.value.toLocaleString("pt-BR")}</span>
    </div>
  )
}

// ── Tipos ──────────────────────────────────────────────────────────────────
type ChannelFilter = "all" | "cazetv" | "getv"

const CHANNEL_LABELS: Record<ChannelFilter, string> = {
  all:    "Todos os canais",
  cazetv: "CazéTV",
  getv:   "GETV",
}

// Retorna TODAS as competições/programas encontrados nos títulos da live
function getLiveCompetitions(live: Live): string[] {
  const titles = live.title_changes?.map((tc: TitleChange) => tc.title)
    ?? live.title_history
    ?? [live.title]
  const comps = new Set(titles.map(parseCompetition))
  return [...comps]
}

// ── Página ─────────────────────────────────────────────────────────────────
export default function HistoricoPage() {
  const [lives,                 setLives]                = useState<Live[]>([])
  const [channel,               setChannel]              = useState<ChannelFilter>("all")
  const [selectedCompetitions,  setSelectedCompetitions] = useState<Set<string>>(new Set())
  const [dateFrom,              setDateFrom]             = useState("")
  const [dateTo,                setDateTo]               = useState("")

  // Cache de categorias por video_id (busca na subcoleção comments, igual HistoricoCard)
  const catCacheRef = useRef<Record<string, Record<string, number>>>({})
  const [catCache,     setCatCache]     = useState<Record<string, Record<string, number>>>({})
  const [fetchingCats, setFetchingCats] = useState(false)

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
            title_changes:      d.title_changes      ?? undefined,
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

  // 1. Filtro por canal (OUTROS incluído — aparece na lista como bucket)
  const channelFiltered = useMemo(() => {
    return lives.filter((l) => {
      if (channel !== "all" && l.channel.toLowerCase() !== channel) return false
      return true
    })
  }, [lives, channel])

  // 2. Lista de competições disponíveis (do canal selecionado) — cada live pode ter várias
  const competitions = useMemo(() => {
    const acc: Record<string, number> = {}
    channelFiltered.forEach((l) => {
      getLiveCompetitions(l).forEach((comp) => {
        acc[comp] = (acc[comp] || 0) + 1
      })
    })
    return Object.entries(acc)
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count)
  }, [channelFiltered])

  // Limpar competições selecionadas ao trocar canal
  useEffect(() => { setSelectedCompetitions(new Set()) }, [channel])

  // 3. Filtro completo (canal + competição + data) — live aparece se QUALQUER competição der match
  const fullyFiltered = useMemo(() => {
    return channelFiltered.filter((l) => {
      if (selectedCompetitions.size > 0) {
        const liveComps = getLiveCompetitions(l)
        if (!liveComps.some((c) => selectedCompetitions.has(c))) return false
      }
      const dateStr = (l.ended_at ?? l.started_at ?? "").slice(0, 10)
      if (dateFrom && dateStr < dateFrom) return false
      if (dateTo   && dateStr > dateTo)   return false
      return true
    })
  }, [channelFiltered, selectedCompetitions, dateFrom, dateTo])

  // 4. Busca categorias da subcoleção comments
  //    Só bloqueia quando NENHUMA competição está selecionada e há muitas lives (tela inicial)
  useEffect(() => {
    if (selectedCompetitions.size === 0 && fullyFiltered.length > 50) return
    const missing = fullyFiltered.filter((l) => !catCacheRef.current[l.video_id])
    if (missing.length === 0) return

    setFetchingCats(true)
    Promise.all(
      missing.map(async (live) => {
        const snap = await getDocs(
          query(collection(db, "lives", live.video_id, "comments"), where("is_technical", "==", true))
        )
        const cats: Record<string, number> = {}
        snap.docs.forEach((d) => {
          const cat = normCat(d.data().category as string | null)
          if (cat) cats[cat] = (cats[cat] || 0) + 1
        })
        catCacheRef.current[live.video_id] = cats
      })
    ).then(() => {
      setCatCache({ ...catCacheRef.current })
      setFetchingCats(false)
    })
  }, [fullyFiltered, selectedCompetitions])

  // 5. Agrega categorias do cache para o pie
  const pieData = useMemo(() => {
    const acc: Record<string, number> = {}
    fullyFiltered.forEach((live) => {
      const cats = catCache[live.video_id] ?? {}
      Object.entries(cats).forEach(([cat, n]) => {
        acc[cat] = (acc[cat] || 0) + n
      })
    })
    return Object.entries(acc)
      .filter(([, v]) => v > 0)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
  }, [fullyFiltered, catCache])

  // 5. Agrupamento por data
  const dateGroups = useMemo(() => {
    const acc: Record<string, Live[]> = {}
    fullyFiltered.forEach((live) => {
      const dateStr = (live.ended_at ?? live.started_at ?? "").slice(0, 10)
      if (!acc[dateStr]) acc[dateStr] = []
      acc[dateStr].push(live)
    })
    return Object.entries(acc)
      .sort(([a], [b]) => b.localeCompare(a))
      .map(([date, groupLives]) => ({ date, groupLives }))
  }, [fullyFiltered])

  const stats = useMemo(() => ({
    count:    fullyFiltered.length,
    msgs:     fullyFiltered.reduce((s, l) => s + l.total_comments, 0),
    problems: fullyFiltered.reduce((s, l) => s + l.technical_comments, 0),
  }), [fullyFiltered])

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
    } catch { return dateStr }
  }

  const pieTotal = pieData.reduce((s, d) => s + d.value, 0)

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="fade-up flex items-center gap-3">
        <History size={16} className="text-white/20" />
        <div>
          <h1 className="text-sm font-bold text-white">Historico</h1>
          <p className="text-[11px] text-white/20 font-mono">
            {lives.length} transmiss{lives.length > 1 ? "oes" : "ao"} encerrada{lives.length > 1 ? "s" : ""}
              {fullyFiltered.length < lives.length && ` · mostrando ${fullyFiltered.length}`}
          </p>
        </div>
      </div>

      {/* Painel: Filtros (esq) + Gráfico (dir) */}
      {lives.length > 0 && (
        <div className="fade-d1 panel overflow-hidden grid grid-cols-2 divide-x divide-white/[0.06]">

          {/* ── Esquerda: filtros ─────────────────────────────────────── */}
          <div className="p-4 space-y-5">

            {/* Canal */}
            <div>
              <p className="text-[8px] font-bold uppercase tracking-wider text-white/30 mb-2">Canal</p>
              <div className="space-y-1.5">
                {(["all", "cazetv", "getv"] as ChannelFilter[]).map((val) => (
                  <button
                    key={val}
                    onClick={() => setChannel(val)}
                    className={`flex items-center gap-2.5 w-full text-left text-[11px] font-mono transition-colors ${
                      channel === val ? "text-white" : "text-white/30 hover:text-white/55"
                    }`}
                  >
                    <span className={`flex-none w-3 h-3 rounded-full border-2 transition-colors ${
                      channel === val ? "border-white bg-white" : "border-white/25"
                    }`} />
                    {CHANNEL_LABELS[val]}
                  </button>
                ))}
              </div>
            </div>

            {/* Filtro por data */}
            <div>
              <p className="text-[8px] font-bold uppercase tracking-wider text-white/30 mb-2">Período</p>
              <div className="flex items-center gap-2">
                <div className="flex-1">
                  <p className="text-[8px] text-white/20 font-mono mb-1">De</p>
                  <input
                    type="date"
                    value={dateFrom}
                    onChange={(e) => setDateFrom(e.target.value)}
                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded px-2 py-1 text-[10px] font-mono text-white/50 [color-scheme:dark] focus:outline-none focus:border-white/20"
                  />
                </div>
                <div className="flex-1">
                  <p className="text-[8px] text-white/20 font-mono mb-1">Até</p>
                  <input
                    type="date"
                    value={dateTo}
                    onChange={(e) => setDateTo(e.target.value)}
                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded px-2 py-1 text-[10px] font-mono text-white/50 [color-scheme:dark] focus:outline-none focus:border-white/20"
                  />
                </div>
                {(dateFrom || dateTo) && (
                  <button
                    onClick={() => { setDateFrom(""); setDateTo("") }}
                    className="text-[9px] font-mono text-white/20 hover:text-white/45 transition-colors mt-4"
                  >
                    ✕
                  </button>
                )}
              </div>
            </div>

            {/* Competição */}
            <div className="flex-1">
              <div className="flex items-center justify-between mb-2">
                <p className="text-[8px] font-bold uppercase tracking-wider text-white/30">Competição</p>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => setSelectedCompetitions(new Set(competitions.map((c) => c.name)))}
                    className="text-[9px] font-mono text-white/25 hover:text-white/50 transition-colors"
                  >
                    marcar todos
                  </button>
                  {selectedCompetitions.size > 0 && (
                    <button
                      onClick={() => setSelectedCompetitions(new Set())}
                      className="text-[9px] font-mono text-white/25 hover:text-white/50 transition-colors"
                    >
                      limpar
                    </button>
                  )}
                </div>
              </div>
              <div className="space-y-0.5 max-h-52 overflow-y-auto pr-1">
                {competitions.map(({ name, count }) => {
                  const active  = selectedCompetitions.has(name)
                  const dimmed  = selectedCompetitions.size > 0 && !active
                  return (
                    <button
                      key={name}
                      onClick={() => toggleCompetition(name)}
                      className={`flex items-center gap-2 w-full text-left px-1 py-[3px] rounded transition-colors ${
                        dimmed ? "text-white/15" : active ? "text-white/85" : "text-white/40 hover:text-white/65"
                      }`}
                    >
                      <span className={`flex-none w-3 h-3 rounded border transition-colors ${
                        active ? "bg-white border-white" : "border-white/20"
                      }`} />
                      <span className="flex-1 text-[10px] font-mono truncate">{name}</span>
                      <span className="text-[9px] font-mono text-white/20 tabular-nums shrink-0">{count}</span>
                    </button>
                  )
                })}
              </div>
            </div>
          </div>

          {/* ── Direita: gráfico de pizza ──────────────────────────────── */}
          <div className="p-4 flex flex-col gap-3">
            <p className="text-[8px] font-bold uppercase tracking-wider text-white/30">
              Categorias de problemas
            </p>

            {selectedCompetitions.size === 0 && fullyFiltered.length > 50 ? (
              <div className="flex-1 flex items-center justify-center text-center px-4">
                <p className="text-white/20 text-[11px] font-mono leading-relaxed">
                  Selecione uma competição<br />para ver o breakdown de categorias
                </p>
              </div>
            ) : fetchingCats ? (
              <div className="flex-1 flex items-center justify-center text-white/20 text-[11px] font-mono">
                carregando...
              </div>
            ) : pieData.length > 0 ? (
              <>
                {/* Donut */}
                <div style={{ height: 150 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={pieData}
                        cx="50%"
                        cy="50%"
                        innerRadius={42}
                        outerRadius={68}
                        paddingAngle={2}
                        dataKey="value"
                        stroke="none"
                        isAnimationActive={false}
                      >
                        {pieData.map((entry) => (
                          <Cell
                            key={entry.name}
                            fill={CAT_COLOR[entry.name] ?? "#ffffff22"}
                          />
                        ))}
                      </Pie>
                      <Tooltip content={<PieTooltip />} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>

                {/* Legenda */}
                <div className="space-y-1.5">
                  {pieData.map(({ name, value }) => {
                    const pct   = pieTotal > 0 ? Math.round((value / pieTotal) * 100) : 0
                    const color = CAT_COLOR[name] ?? "#ffffff22"
                    return (
                      <div key={name} className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
                        <span className="text-[10px] font-mono text-white/45 flex-1 uppercase">{name}</span>
                        <div className="flex-1 h-0.5 bg-white/[0.06] rounded-full overflow-hidden">
                          <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
                        </div>
                        <span className="text-[9px] font-mono text-white/25 w-7 text-right tabular-nums">{pct}%</span>
                        <span className="text-[11px] font-data font-bold w-10 text-right tabular-nums" style={{ color }}>
                          {value.toLocaleString("pt-BR")}
                        </span>
                      </div>
                    )
                  })}
                </div>

                {/* Mini stats */}
                <div className="mt-auto pt-3 border-t border-white/[0.06] flex gap-4 text-[9px] font-mono text-white/25">
                  <span>{stats.count} live{stats.count > 1 ? "s" : ""}</span>
                  <span>{stats.msgs.toLocaleString("pt-BR")} msgs</span>
                  <span className="text-red-400/50">{stats.problems.toLocaleString("pt-BR")} problemas</span>
                </div>
              </>
            ) : (
              <div className="flex-1 flex items-center justify-center text-white/20 text-xs font-mono">
                Sem dados de problemas
              </div>
            )}
          </div>
        </div>
      )}

      {/* Date groups */}
      {fullyFiltered.length > 0 && (
        <div className="fade-d2 space-y-6">
          {dateGroups.map(({ date, groupLives }) => (
            <div key={date} className="space-y-4">
              <div className="flex items-center gap-3">
                <span className="text-[10px] font-bold font-mono text-white/25 shrink-0">
                  {formatDateGroup(date)}
                </span>
                <div className="flex-1 h-px bg-white/[0.06]" />
                <span className="text-[10px] font-mono text-white/15 shrink-0">{groupLives.length}</span>
              </div>
              {groupLives.map((live) => (
                <HistoricoCard key={live.video_id} live={live} />
              ))}
            </div>
          ))}
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

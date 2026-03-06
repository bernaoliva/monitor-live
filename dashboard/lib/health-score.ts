export interface HealthScoreResult {
  score: number
  level: "OK" | "ATENÇÃO" | "ALERTA" | "CRÍTICO"
  color: string
}

function commentWeight(severity: string, issue: string | null): number {
  const base = severity === "high" ? 2.0 : severity === "medium" ? 1.0 : 0.3
  if (!issue) return base
  const u = issue.toLowerCase()
  if (u.includes("tela") || u.includes("black"))            return base + 1.0
  if (u.includes("audio") || u.includes("áudio") || u.includes("som")) return base + 1.0
  if (u.includes("vazamento"))                               return base + 0.5
  if (u.includes("conexao") || u.includes("conexão") || u.includes("sinal") || u.includes("caiu")) return base + 0.5
  return base
}

function linearSlope(values: number[]): number {
  const n = values.length
  if (n < 2) return 0
  const xm = (n - 1) / 2
  const ym = values.reduce((s, v) => s + v, 0) / n
  let num = 0, den = 0
  for (let i = 0; i < n; i++) {
    num += (i - xm) * (values[i] - ym)
    den += (i - xm) ** 2
  }
  return den === 0 ? 0 : num / den
}

export function computeHealthScore(
  viewers: number,
  comments: Array<{ ts: string; severity: string; issue: string | null }>,
  minutesData: Array<{ minute: string; technical: number }>,
): HealthScoreResult {
  const sorted = [...minutesData].sort((a, b) => a.minute.localeCompare(b.minute))
  const logV   = Math.log10(Math.max(viewers, 100))
  const now    = Date.now()

  // 1. Base Load — densidade nos últimos 10 min
  const cutoff = now - 10 * 60 * 1000
  let weighted10 = 0
  for (const c of comments) {
    try {
      const t = new Date(c.ts.replace(" ", "T")).getTime()
      if (!isNaN(t) && t >= cutoff) weighted10 += commentWeight(c.severity, c.issue)
    } catch { /* ts malformado */ }
  }
  const basePenalty = Math.min((weighted10 / logV) * 1.3, 60)

  // 2. Spike — avg_3min vs avg_10min
  const techVals = sorted.map((p) => p.technical)
  const last10   = techVals.slice(-10)
  const last3    = techVals.slice(-3)
  const avg10    = last10.length ? last10.reduce((s, v) => s + v, 0) / last10.length : 0
  const avg3     = last3.length  ? last3.reduce((s, v)  => s + v, 0) / last3.length  : 0
  const ratio    = avg3 / Math.max(avg10, 0.3)
  const spikePenalty = ratio > 2.0 ? Math.min(Math.log2(ratio) * 7, 25) : 0

  // 3. Velocity — inclinação dos últimos 5 min
  const slope = linearSlope(techVals.slice(-5))
  const velocityPenalty = slope > 0 ? Math.min(slope * 1.5, 15) : 0

  // 4. Histórico acumulado
  const cumulWeighted = comments.reduce((s, c) => s + commentWeight(c.severity, c.issue), 0)
  const msgPenalty = Math.min((cumulWeighted / logV) * 0.5, 30)

  let spikeIntensity = 0
  for (const p of sorted) {
    if (p.technical >= 3) spikeIntensity += Math.floor(p.technical / 3)
  }
  const history = Math.min(msgPenalty + Math.min(spikeIntensity, 40), 55)

  // Score final
  const realtime = Math.min(basePenalty + spikePenalty + velocityPenalty, 60)
  const score    = Math.max(0, Math.floor(100 - realtime - history))

  const level = score >= 80 ? "OK" : score >= 50 ? "ATENÇÃO" : score >= 25 ? "ALERTA" : "CRÍTICO"
  const color = score >= 80 ? "#22c55e" : score >= 50 ? "#eab308" : score >= 25 ? "#f97316" : "#ef4444"

  return { score, level, color }
}

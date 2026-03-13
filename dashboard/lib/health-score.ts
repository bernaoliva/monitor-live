export interface HealthScoreResult {
  score: number
  level: "OK" | "ATENÇÃO" | "ALERTA" | "CRÍTICO"
  color: string
}

export function computeHealthScore(
  viewers: number,
  comments: Array<{ ts: string; severity: string; issue: string | null }>,
  minutesData: Array<{ minute: string; technical: number; total?: number; viewers?: number }>,
): HealthScoreResult {
  const sorted = [...minutesData].sort((a, b) => a.minute.localeCompare(b.minute))
  const n = sorted.length
  const techCount = comments.length

  if (n === 0 || techCount === 0) {
    return { score: 100, level: "OK", color: "#22c55e" }
  }

  const totalMsgs = sorted.reduce((s, p) => s + (p.total ?? 0), 0)
  const ratePercent = totalMsgs > 0 ? (techCount / totalMsgs) * 100 : 0

  // --- Fator de audiência ---
  // Pesa cada problema pela significância dado o tamanho da audiência.
  // Chat pequeno → cada reclamação é mais grave (fator > 1)
  // Chat enorme → reclamações diluídas por ruído/falso positivo (fator < 1)
  let viewerWeightedSum = 0, techWithViewers = 0
  for (const p of sorted) {
    if (p.technical > 0 && (p.viewers ?? 0) > 0) {
      viewerWeightedSum += (p.viewers ?? 0) * p.technical
      techWithViewers += p.technical
    }
  }
  const fallbackViewers = viewers > 0 ? viewers : 100_000
  const avgProblemViewers = techWithViewers > 0
    ? viewerWeightedSum / techWithViewers
    : fallbackViewers
  // ~100k → 1.0 | ~1M → 0.83 | ~1k → 1.67 | ~500 → 1.85
  const audienceFactor = Math.min(Math.max(
    5 / Math.log10(Math.max(avgProblemViewers, 100)),
    0.6,
  ), 2.0)

  // 1. Count penalty: ajustado pelo fator de audiência
  const effectiveTech = techCount * audienceFactor
  const countPenalty = Math.min(effectiveTech * 0.9, 45)

  // 2. Rate penalty: curva sqrt na taxa % (já normaliza por volume de msgs)
  const ratePenalty = Math.min(Math.sqrt(ratePercent) * 11, 60)

  // Base: a dimensão pior domina
  const basePenalty = Math.max(countPenalty, ratePenalty)

  // 3. Peak penalty: excesso da pior janela de 3 min sobre a média
  //    Só ativa após 10 minutos de dados (evita ruído no início)
  let worstWindowRate = 0
  if (n >= 10) {
    for (let i = 0; i <= n - 3; i++) {
      const wTech = sorted[i].technical + sorted[i + 1].technical + sorted[i + 2].technical
      const wTotal = (sorted[i].total ?? 0) + (sorted[i + 1].total ?? 0) + (sorted[i + 2].total ?? 0)
      if (wTotal > 0) {
        worstWindowRate = Math.max(worstWindowRate, (wTech / wTotal) * 100)
      }
    }
  }
  const peakExcess = Math.max(0, worstWindowRate - ratePercent)
  const peakPenalty = Math.min(Math.sqrt(peakExcess) * 5, 10)

  // 4. Severity: comentários high adicionam penalidade extra
  const highCount = comments.filter((c) => c.severity === "high").length
  const severityPenalty = Math.min(highCount * 0.8, 8)

  // 5. Recovery: minutos limpos após último problema → bônus
  //    Dois modos: fração (bom para lives curtas) e absoluto com sqrt
  //    (bom para lives longas onde a fração dilui). Usa o maior dos dois.
  let lastProblemIdx = -1
  for (let i = n - 1; i >= 0; i--) {
    if (sorted[i].technical > 0) { lastProblemIdx = i; break }
  }
  const cleanMinutes = lastProblemIdx >= 0 ? n - 1 - lastProblemIdx : n
  const fractionRecovery = (cleanMinutes / Math.max(n, 1)) * 15
  const absoluteRecovery = Math.sqrt(cleanMinutes) * 0.8
  const recoveryBonus = Math.min(Math.max(fractionRecovery, absoluteRecovery), 14)

  const raw = 100 - basePenalty - peakPenalty - severityPenalty + recoveryBonus
  const score = Math.max(0, Math.min(100, Math.floor(raw)))

  const level = score >= 80 ? "OK" : score >= 50 ? "ATENÇÃO" : score >= 25 ? "ALERTA" : "CRÍTICO"
  const color = score >= 80 ? "#22c55e" : score >= 50 ? "#eab308" : score >= 25 ? "#f97316" : "#ef4444"

  return { score, level, color }
}

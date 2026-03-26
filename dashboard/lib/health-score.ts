export interface HealthScoreResult {
  score: number
  level: "OK" | "ATENÇÃO" | "ALERTA" | "CRÍTICO"
  color: string
}

export function computeHealthScore(
  viewers: number,
  comments: Array<{ ts: string; severity: string; issue: string | null }>,
  minutesData: Array<{ minute: string; technical: number; total?: number; viewers?: number; f_count?: number }>,
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
  // ~100k → 0.80 | ~500k → 0.70 | ~1M → 0.67 | ~1k → 1.33 | ~500 → 1.48
  const audienceFactor = Math.min(Math.max(
    4 / Math.log10(Math.max(avgProblemViewers, 100)),
    0.4,
  ), 2.0)

  // 0. F surge: contar F surges como problemas reais (antes do cálculo de penalties)
  let fSurgeCount = 0
  let fSurgePenalty = 0
  for (const m of sorted) {
    const fCount = m.f_count ?? 0
    const mViewers = m.viewers ?? fallbackViewers
    const fThreshold = Math.max(30, Math.floor(mViewers * 0.0002))
    if (fCount >= fThreshold && m.technical >= 2) {
      fSurgeCount += fCount
      const af = Math.min(Math.max(4 / Math.log10(Math.max(mViewers, 100)), 0.4), 2.0)
      fSurgePenalty += Math.sqrt(fCount / fThreshold) * 3 * af
    }
  }
  fSurgePenalty = Math.min(fSurgePenalty, 12)
  const totalProblems = techCount + fSurgeCount

  // 1. Count penalty: taxa por minuto ajustada pela audiência
  const totalRatePercent = totalMsgs > 0 ? (totalProblems / totalMsgs) * 100 : 0
  const effectiveTech = totalProblems * audienceFactor
  const techRate = effectiveTech / Math.max(n, 1)
  const countPenalty = Math.min(Math.sqrt(techRate) * 20, 45)

  // 2. Rate penalty: curva sqrt na taxa % (inclui F surges)
  const ratePenalty = Math.min(Math.sqrt(totalRatePercent) * 11, 60)

  // Base: a dimensão pior domina
  const basePenalty = Math.max(countPenalty, ratePenalty)

  // 3. Absolute penalty: penalidade por volume bruto de problemas
  const absolutePenalty = Math.min(Math.sqrt(totalProblems) * 1.2, 17)

  // 4. Peak penalty: excesso da pior janela de 3 min sobre a média
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
  const peakExcess = Math.max(0, worstWindowRate - totalRatePercent)
  const peakPenalty = Math.min(Math.sqrt(peakExcess) * 5, 10)

  // 5. Severity: comentários high adicionam penalidade extra
  const highCount = comments.filter((c) => c.severity === "high").length
  const severityPenalty = Math.min(highCount * 0.8 * audienceFactor, 8)

  // 6. Recovery: tempo real desde o último problema técnico até AGORA
  //    Usa o relógio atual, não o último doc — funciona mesmo em lives com chat esparso
  //    onde não existem docs de minuto intermediários.
  let lastTechMinute = ""
  for (let i = n - 1; i >= 0; i--) {
    if (sorted[i].technical > 0) { lastTechMinute = sorted[i].minute; break }
  }
  let cleanMinutes = 0
  if (lastTechMinute) {
    const tLast = new Date(lastTechMinute + ":00").getTime()
    const tNow  = Date.now()
    if (!isNaN(tLast)) {
      cleanMinutes = Math.max(0, Math.floor((tNow - tLast) / 60000))
    }
  } else {
    cleanMinutes = n // nenhum técnico = tudo limpo
  }
  // n estimado: usa duração real da live (primeiro minuto até agora) se maior que docs
  const firstMinute = sorted[0]?.minute ?? ""
  let liveDurationMin = n
  if (firstMinute) {
    const tFirst = new Date(firstMinute + ":00").getTime()
    if (!isNaN(tFirst)) {
      liveDurationMin = Math.max(n, Math.floor((Date.now() - tFirst) / 60000))
    }
  }
  const fractionRecovery = (cleanMinutes / Math.max(liveDurationMin, 1)) * 12
  const absoluteRecovery = Math.sqrt(cleanMinutes) * 0.7
  const recoveryBonus = Math.min(Math.max(fractionRecovery, absoluteRecovery), 10)

  const raw = 100 - basePenalty - absolutePenalty - peakPenalty - severityPenalty - fSurgePenalty + recoveryBonus
  const score = Math.max(0, Math.min(100, Math.floor(raw)))

  const level = score >= 80 ? "OK" : score >= 50 ? "ATENÇÃO" : score >= 25 ? "ALERTA" : "CRÍTICO"
  const color = score >= 80 ? "#22c55e" : score >= 50 ? "#eab308" : score >= 25 ? "#f97316" : "#ef4444"

  return { score, level, color }
}

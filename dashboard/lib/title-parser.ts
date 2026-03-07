const NOISE: RegExp[] = [
  /^\d+[ªºaAoO]\s*RODADA$/i,
  /^(PLAYOFFS|FINAL|SEMIFINAL|QUARTAS|OITAVAS)/i,
  /^\d+[ªºoO]\s*DIA$/i,
  /^(GE\s*TV|GETV|SPORTV|GE\.GLOBO)/i,
  /^#/,
  /^\d{4}\/\d{2,4}$/,
]

function stripYear(s: string): string {
  return s.replace(/\s*\d{2,4}\/\d{2,4}\s*$/, "").replace(/\s*\d{4}\s*$/, "").trim()
}

export function parseCompetition(title: string): string {
  const parts = (title || "").split("|").map((s) => s.trim().toUpperCase()).filter(Boolean)
  if (parts.length < 2) return "OUTROS"

  for (let i = parts.length - 1; i >= 1; i--) {
    if (NOISE.some((re) => re.test(parts[i]))) continue
    return stripYear(parts[i]) || "OUTROS"
  }
  return "OUTROS"
}

export function extractCompetitions(titles: string[]): { name: string; count: number }[] {
  const acc: Record<string, number> = {}
  titles.forEach((t) => {
    const comp = parseCompetition(t)
    acc[comp] = (acc[comp] || 0) + 1
  })
  return Object.entries(acc)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => {
      if (a.name === "OUTROS") return 1
      if (b.name === "OUTROS") return -1
      return b.count - a.count
    })
}

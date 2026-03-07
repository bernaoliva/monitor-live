// Segmentos que NÃO são o nome da competição
const NOISE: RegExp[] = [
  /^\d+[ªº][ª]?\s*RODADA/i,                                      // "25ª RODADA"
  /^(PLAYOFFS?|FINAL|SEMIFINAL|QUARTAS?(\s+DE\s+FINAL)?|OITAVAS?(\s+DE\s+FINAL)?|DEZESSEIS)/i,
  /^\d+[ªºoO]\s*DIA$/i,                                          // "3º DIA"
  /^(GE\s*TV|GETV|SPORTV|GE\.GLOBO|PANELA\s+SPORTV)/i,          // broadcasters
  /^#/,                                                            // hashtags
  /^\d{4}\/\d{2,4}$/,                                             // "2025/2026" sozinho
  /\bX\b/,                                                         // nomes de partida ("NORUEGA X SUÍÇA")
  /^(ABERTURA|ENCERRAMENTO|QUALIFICATÓRIAS?|DUPLAS?|SIMPLES|CURLING|HÓQUEI|MISTO|MASCULINO|FEMININO)$/i,
  /^EP\s*#?\d+$/i,                                                 // números de episódio
]

function stripYear(s: string): string {
  return s
    .replace(/\s*\b(19|20)\d{2}\s*\/\s*\d{2,4}\b\s*$/, "") // "2025/2026" ou "25/26"
    .replace(/\s*\b(19|20)\d{2}\b\s*$/, "")                 // "2026" sozinho
    .trim()
}

function cleanSegment(raw: string): string {
  return raw.replace(/^[:\-–—]\s*/, "").trim().toUpperCase()
}

export function parseCompetition(title: string): string {
  const parts = (title || "")
    .split("|")
    .map(cleanSegment)
    .filter(Boolean)

  if (parts.length < 2) return "OUTROS"

  // Varrer a partir do segmento [1] (pular o nome do jogo em [0])
  for (let i = 1; i < parts.length; i++) {
    if (NOISE.some((re) => re.test(parts[i]))) continue
    return stripYear(parts[i]) || "OUTROS"
  }

  // Fallback: se [0] não for nome de jogo (sem " X "), usar [0]
  if (!/\bX\b/.test(parts[0]) && !/^AO\s+VIVO/i.test(parts[0])) {
    return stripYear(parts[0]) || "OUTROS"
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

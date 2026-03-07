// Segmentos que NÃO são o nome da competição
const NOISE: RegExp[] = [
  /^\d+[ªº][ª]?\s*RODADA/i,
  /^(PLAYOFFS?|FINAL(IS)?|SEMIFINAL(IS)?|QUARTAS?(\s+DE\s+FINAL)?|OITAVAS?(\s+DE\s+FINAL)?|DEZESSEIS)/i,
  /^\d+[ªºoO]\s*DIA$/i,
  /^(GE\s*TV|GETV|SPORTV|GE\.GLOBO|PANELA\s+SPORTV)/i,
  /^#/,
  /^\d{4}\/\d{2,4}$/,
  /\bX\b/,
  /^(ABERTURA|ENCERRAMENTO|QUALIFICATÓRIAS?|DUPLAS?|SIMPLES|CURLING|HÓQUEI|MISTO|MASCULINO|FEMININO)$/i,
  /^EP\s*#?\d+$/i,
  /^UM\s+DIA\s+COM\b/i,   // programa, não competição
]

// Normaliza variações para o nome canônico da competição
const ALIASES: [RegExp, string][] = [
  [/SINGAPURA\s+SMASH/i,              "SINGAPURA SMASH"],
  [/OLIMP[IÍ]ADAS?\s+DE\s+INVERNO/i, "OLIMPÍADAS DE INVERNO"],
  [/NOCHE\s+DE\s+COPA/i,             "LIBERTADORES"],
  [/RECOPA\s+SUL.?AMERICANA/i,       "RECOPA SUL-AMERICANA"],
  [/COPA\s+SUL.?AMERICANA/i,         "COPA SULAMERICANA"],
  [/\bSUL.?AMERICANA\b/i,            "COPA SULAMERICANA"],
]

function resolveAlias(name: string): string {
  for (const [re, norm] of ALIASES) {
    if (re.test(name)) return norm
  }
  return name
}

function stripYear(s: string): string {
  return s
    .replace(/\s*\b(19|20)\d{2}\s*\/\s*\d{2,4}\b\s*$/, "")
    .replace(/\s*\b(19|20)\d{2}\b\s*$/, "")
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

  // Verificar aliases direto nos segmentos (captura variações dentro de qualquer posição)
  for (const [re, norm] of ALIASES) {
    if (re.test(parts.join("|"))) {
      // Confirmar que pelo menos um segmento não-[0] tem o alias
      for (let i = 1; i < parts.length; i++) {
        if (re.test(parts[i])) return norm
      }
    }
  }

  // Varrer a partir do segmento [1] (pular nome do jogo em [0])
  for (let i = 1; i < parts.length; i++) {
    if (NOISE.some((re) => re.test(parts[i]))) continue
    const result = stripYear(parts[i])
    return result ? resolveAlias(result) : "OUTROS"
  }

  // Fallback: se [0] não for nome de jogo (sem " X "), usar [0]
  if (!/\bX\b/.test(parts[0]) && !/^AO\s+VIVO/i.test(parts[0])) {
    const result = stripYear(parts[0])
    return result ? resolveAlias(result) : "OUTROS"
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

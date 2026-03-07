// ── Competições conhecidas (ordem: mais específico primeiro) ──────────────
const COMPETITIONS: [RegExp, string][] = [
  // Olimpíadas
  [/OLIMP[IÍ]ADAS?\s+DE\s+INVERNO/i,                       "OLIMPÍADAS DE INVERNO"],

  // Futebol europeu
  [/CONFERENCE\s+LEAGUE/i,                                   "CONFERENCE LEAGUE"],
  [/EUROPA\s+LEAGUE/i,                                       "EUROPA LEAGUE"],
  [/BUNDESLIGA/i,                                            "BUNDESLIGA"],
  [/LIGUE\s*1/i,                                             "LIGUE 1"],
  [/LA\s+LIGA/i,                                             "LA LIGA"],
  [/PREMIER\s+LEAGUE/i,                                      "PREMIER LEAGUE"],
  [/SÉRIE\s+A\s+ITALIANA|SERIE\s+A\s+ITALIANA/i,            "SÉRIE A ITALIANA"],

  // Futebol brasileiro
  [/COPA.*BRASIL.*FEM[A-Z]*|COPA.*FEM[A-Z]*.*BRASIL/i,      "COPA DO BRASIL FEMININO"],
  [/COPA\s+DO\s+BRASIL/i,                                    "COPA DO BRASIL"],
  [/BRASILEIR[AÃ]O|CAMPEONATO\s+BRASILEIRO/i,                "BRASILEIRÃO"],
  [/CAMPEONATO\s+MINEIRO/i,                                  "CAMPEONATO MINEIRO"],
  [/CAMPEONATO\s+CARIOCA|\bCARIOCA\b/i,                      "CAMPEONATO CARIOCA"],

  // Futebol sul-americano
  [/RECOPA\s+SUL.?AMERICANA/i,                               "RECOPA SUL-AMERICANA"],
  [/COPA\s+SUL.?AMERICANA/i,                                 "COPA SULAMERICANA"],
  [/\bSUL.?AMERICANA\b/i,                                    "COPA SULAMERICANA"],
  [/LIBERTADORES|NOCHE\s+DE\s+COPA/i,                        "LIBERTADORES"],

  // Futebol internacional
  [/ELIMINATÓRIAS.*BASQUETE|BASQUETE.*ELIMINATÓRIAS/i,        "ELIMINATÓRIAS BASQUETE"],
  [/ELIMINATÓRIAS/i,                                         "ELIMINATÓRIAS"],
  [/AMISTOSO/i,                                              "AMISTOSO"],

  // Tênis de mesa / outros esportes
  [/SINGAPURA\s+SMASH/i,                                     "SINGAPURA SMASH"],
  [/GRAND\s+SLAM/i,                                          "GRAND SLAM"],
  [/GRAND\s+PRIX/i,                                          "GRAND PRIX"],
  [/ATP\s+CHALLENGER/i,                                      "ATP CHALLENGER"],
  [/COPA.*V[OÔ]LEI/i,                                        "COPA BRASIL DE VÔLEI"],
]

// ── Programas conhecidos ───────────────────────────────────────────────────
const PROGRAMS: [RegExp, string][] = [
  [/GERAL\s+CAZ[EÉ]TV/i,      "GERAL CAZÉTV"],
  [/RODA\s+DE\s+BOBO/i,       "RODA DE BOBO"],
  [/RECOPANDO/i,               "RECOPANDO"],
  [/TÁ\s+ON|TA\s+ON/i,        "TÁ ON"],
  [/TROPA\s+GE\s+TV/i,        "TROPA GE TV"],
  [/SUPERLIVE/i,               "SUPERLIVE"],
  [/LÉRIGOU|LERIGOU/i,         "LÉRIGOU"],
  [/DESTRINCHA\s+DONAN/i,      "DESTRINCHA DONAN"],
  [/UM\s+DIA\s+COM/i,          "UM DIA COM"],
]

export function parseCompetition(title: string): string {
  const t = (title || "").toUpperCase()

  for (const [re, name] of COMPETITIONS) {
    if (re.test(t)) return name
  }

  for (const [re, name] of PROGRAMS) {
    if (re.test(t)) return name
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

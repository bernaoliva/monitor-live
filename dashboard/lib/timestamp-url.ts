export function youtubeTimestampUrl(
  videoUrl: string,
  startedAt: string,
  minuteKey: string,
): string | null {
  if (!videoUrl || !startedAt) return null

  let target: Date
  if (minuteKey.includes("T")) {
    target = new Date(minuteKey)
  } else {
    // Legacy "HH:mm" format — use date from startedAt
    const dateMatch = startedAt.match(/^\d{4}-\d{2}-\d{2}/)
    if (!dateMatch) return null
    target = new Date(`${dateMatch[0]}T${minuteKey}`)
  }

  const start = new Date(startedAt)
  const offsetSec = Math.floor((target.getTime() - start.getTime()) / 1000)

  // Offset negativo ou > 24h = referência errada (ex: started_at gravado no restart)
  if (offsetSec < 0 || offsetSec > 86400) return null

  // t=0 numa live faz o YouTube ir pro live edge — usar mínimo de 1s
  const t = Math.max(1, offsetSec)

  const sep = videoUrl.includes("?") ? "&" : "?"
  return `${videoUrl}${sep}t=${t}s`
}

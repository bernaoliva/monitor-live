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
  let offsetSec = Math.floor((target.getTime() - start.getTime()) / 1000)

  // Midnight crossing: if offset is negative, add 24h
  if (offsetSec < 0) offsetSec += 86400

  const sep = videoUrl.includes("?") ? "&" : "?"
  return `${videoUrl}${sep}t=${offsetSec}s`
}

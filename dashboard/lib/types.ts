export type Severity = "none" | "low" | "medium" | "high"

export interface Live {
  video_id: string
  channel: string
  title: string
  url: string
  status: "active" | "ended"
  started_at: string
  ended_at: string | null
  last_seen_at: string
  total_comments: number
  technical_comments: number
  issue_counts: Record<string, number>
}

export interface Comment {
  id: string
  author: string
  text: string
  ts: string
  is_technical: boolean
  category: string | null
  issue: string | null
  severity: Severity
}

export interface ChartPoint {
  minute: string
  total: number
  technical: number
}

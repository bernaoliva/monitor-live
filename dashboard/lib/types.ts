export type Severity = "none" | "low" | "medium" | "high"
export type CardDensity = "full" | "compact" | "mini"

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
  concurrent_viewers?: number
  gpu_active?: boolean
  title_history?: string[]
  title_changes?: TitleChange[]
}

export interface TitleChange {
  title: string
  ts: string
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
  synthetic?: boolean
  model_confidence?: number
  classification_method?: string
  model_version?: string
  dismissed_by_admin?: boolean
}

export interface ChartPoint {
  minute: string
  total: number
  technical: number
  viewers?: number
  f_count?: number
}

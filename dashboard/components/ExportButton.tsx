"use client"

import { MutableRefObject } from "react"
import { Comment } from "@/lib/types"
import { Download } from "lucide-react"
import { format } from "date-fns"

interface Props {
  videoId: string
  title: string
  comments: MutableRefObject<Comment[]>
}

export default function ExportButton({ videoId, title, comments }: Props) {
  function exportCSV() {
    const rows = [...comments.current].reverse()
    const header = ["timestamp", "autor", "comentario", "tecnico", "categoria", "issue", "severidade"]
    const lines  = rows.map((c) => [
      c.ts,
      `"${c.author.replace(/"/g, '""')}"`,
      `"${c.text.replace(/"/g, '""')}"`,
      c.is_technical ? "sim" : "não",
      c.category  ?? "",
      c.issue     ?? "",
      c.severity,
    ].join(","))

    const csv     = [header.join(","), ...lines].join("\n")
    const blob    = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8;" })
    const url     = URL.createObjectURL(blob)
    const anchor  = document.createElement("a")
    const ts      = format(new Date(), "yyyy-MM-dd_HH-mm")
    anchor.href     = url
    anchor.download  = `log_${videoId}_${ts}.csv`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  function exportJSON() {
    const data = {
      video_id:    videoId,
      title,
      exported_at: new Date().toISOString(),
      comments:    [...comments.current].reverse(),
    }
    const blob    = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" })
    const url     = URL.createObjectURL(blob)
    const anchor  = document.createElement("a")
    const ts      = format(new Date(), "yyyy-MM-dd_HH-mm")
    anchor.href     = url
    anchor.download  = `log_${videoId}_${ts}.json`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="flex gap-2 shrink-0">
      <button
        onClick={exportCSV}
        className="flex items-center gap-2 px-3 py-2 text-xs font-semibold text-white/60 bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl transition-all"
      >
        <Download size={13} /> CSV
      </button>
      <button
        onClick={exportJSON}
        className="flex items-center gap-2 px-3 py-2 text-xs font-semibold text-white/60 bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl transition-all"
      >
        <Download size={13} /> JSON
      </button>
    </div>
  )
}

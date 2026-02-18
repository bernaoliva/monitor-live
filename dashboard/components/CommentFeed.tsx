"use client"

import { Comment } from "@/lib/types"
import { format } from "date-fns"
import { AlertTriangle, X } from "lucide-react"

function normalizeCategory(raw: string | null | undefined): string | null {
  if (!raw) return null
  const u = raw.toUpperCase().trim()
  if (/AUDIO|ÁUDIO|SOM\b|NARR/.test(u)) return "AUDIO"
  if (/VIDEO|VÍDEO|TELA|PIXEL|IMAG|CONGEL/.test(u)) return "VIDEO"
  if (/REDE|PLATAFORMA|BUFFER|CAIU|PLAT/.test(u)) return "REDE"
  if (/\bGC\b|PLACAR/.test(u)) return "GC"
  return u
}

const CAT_STYLE: Record<string, { text: string; bg: string }> = {
  AUDIO: { text: "text-blue-300",   bg: "bg-blue-500/10 border-blue-500/20" },
  VIDEO: { text: "text-purple-300", bg: "bg-purple-500/10 border-purple-500/20" },
  REDE:  { text: "text-orange-300", bg: "bg-orange-500/10 border-orange-500/20" },
  GC:    { text: "text-cyan-300",   bg: "bg-cyan-500/10 border-cyan-500/20" },
}

const SEVERITY_STYLES: Record<string, string> = {
  high:   "border-red-500/30 bg-red-500/5",
  medium: "border-orange-500/30 bg-orange-500/5",
  low:    "border-yellow-500/20 bg-yellow-500/5",
  none:   "border-transparent bg-transparent",
}

const SEVERITY_BADGE: Record<string, string> = {
  high:   "bg-red-500/20 text-red-300",
  medium: "bg-orange-500/20 text-orange-300",
  low:    "bg-yellow-500/20 text-yellow-300",
}

export default function CommentFeed({
  comments,
  onDismiss,
}: {
  comments: Comment[]
  onDismiss?: (c: Comment) => void
}) {
  if (comments.length === 0) {
    return (
      <div className="py-16 text-center text-white/30 text-sm">
        Nenhum comentário ainda...
      </div>
    )
  }

  return (
    <div className="divide-y divide-white/[0.04] max-h-[520px] overflow-y-auto">
      {comments.map((c) => {
        const catKey   = normalizeCategory(c.category)
        const catStyle = catKey ? (CAT_STYLE[catKey] ?? null) : null
        return (
          <div
            key={c.id}
            className={`px-5 py-3 flex gap-3 transition-colors border-l-2 group ${
              c.is_technical ? (SEVERITY_STYLES[c.severity] ?? SEVERITY_STYLES.none) : "border-transparent"
            }`}
          >
            {/* Ícone de alerta para técnicos */}
            <div className="pt-0.5 shrink-0 w-4">
              {c.is_technical && (
                <AlertTriangle
                  size={14}
                  className={
                    c.severity === "high"   ? "text-red-400" :
                    c.severity === "medium" ? "text-orange-400" : "text-yellow-400"
                  }
                />
              )}
            </div>

            {/* Conteúdo */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                <span className="text-xs font-semibold text-white/55 truncate max-w-[140px]">
                  {c.author}
                </span>
                <span className="text-[10px] text-white/30 font-mono shrink-0">
                  {format(new Date(c.ts), "HH:mm:ss")}
                </span>
                {c.is_technical && c.severity && c.severity !== "none" && (
                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${SEVERITY_BADGE[c.severity] ?? ""}`}>
                    {c.severity.toUpperCase()}
                  </span>
                )}
                {c.is_technical && catKey && (
                  <span className={`text-[9px] font-bold font-mono px-1.5 py-0.5 rounded border ${catStyle?.bg ?? "bg-white/[0.04] border-white/[0.06]"} ${catStyle?.text ?? "text-white/40"}`}>
                    {catKey}
                  </span>
                )}
              </div>

              <p className={`text-sm leading-relaxed ${c.is_technical ? "text-white/85" : "text-white/50"}`}>
                {c.text}
              </p>

              {c.is_technical && c.issue && (
                <span className="inline-block mt-1 text-[9px] text-white/35 font-mono">
                  {c.issue}
                </span>
              )}
            </div>

            {/* Botão descartar — só para técnicos, aparece no hover */}
            {c.is_technical && onDismiss && (
              <button
                onClick={() => onDismiss(c)}
                title="Descartar: marcar como não-técnico"
                className="opacity-0 group-hover:opacity-100 transition-opacity shrink-0 mt-0.5 text-white/25 hover:text-red-400/70"
              >
                <X size={11} />
              </button>
            )}
          </div>
        )
      })}
    </div>
  )
}

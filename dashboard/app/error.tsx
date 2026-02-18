"use client"

import { useEffect } from "react"
import { AlertTriangle } from "lucide-react"

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error("Dashboard error:", error)
  }, [error])

  return (
    <div className="flex flex-col items-center justify-center py-24 text-center space-y-4">
      <AlertTriangle size={40} className="text-red-400/60" />
      <h2 className="text-lg font-semibold text-white/70">Algo deu errado</h2>
      <p className="text-sm text-white/30 max-w-md">
        {error.message || "Erro inesperado ao carregar a página."}
      </p>
      <button
        onClick={reset}
        className="px-4 py-2 text-sm font-medium text-white bg-white/10 hover:bg-white/15 rounded-lg border border-white/10 transition-colors"
      >
        Tentar novamente
      </button>
    </div>
  )
}

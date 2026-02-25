"use client"

import { useAuth } from "@/lib/auth-context"

export default function LoginScreen() {
  const { signInWithGoogle, error, loading } = useAuth()

  return (
    <div className="min-h-screen bg-bg noise-bg flex flex-col items-center justify-center">
      <div className="w-full max-w-sm px-6 space-y-8">
        {/* Logo */}
        <div className="flex flex-col items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="relative w-2.5 h-2.5">
              <div className="absolute inset-0 rounded-full bg-red-500 pulse-dot" />
              <div className="absolute inset-0 rounded-full bg-red-500" />
            </div>
            <span className="font-bold text-base text-white tracking-tight">MONITOR</span>
          </div>
          <p className="text-[11px] text-white/25 font-mono tracking-wider text-center">
            Monitor de Lives · CazeTV + GETV
          </p>
        </div>

        {/* Card de login */}
        <div className="panel p-6 space-y-5">
          <div className="space-y-1 text-center">
            <p className="text-sm font-semibold text-white">Entrar</p>
            <p className="text-[11px] text-white/30 font-mono">Acesso restrito a @livemode.com</p>
          </div>

          <button
            onClick={signInWithGoogle}
            disabled={loading}
            className="w-full flex items-center justify-center gap-2.5 px-4 py-2.5 rounded-lg bg-white/[0.06] hover:bg-white/[0.10] border border-white/[0.08] hover:border-white/[0.14] text-white text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {/* Google icon */}
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/>
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
            </svg>
            Entrar com Google
          </button>

          {error && (
            <p className="text-[11px] text-red-400/80 font-mono text-center">{error}</p>
          )}
        </div>
      </div>
    </div>
  )
}

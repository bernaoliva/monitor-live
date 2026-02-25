"use client"

import { useAuth } from "@/lib/auth-context"
import LoginScreen from "@/components/LoginScreen"

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen bg-bg flex items-center justify-center">
        <div className="w-1.5 h-1.5 rounded-full bg-white/20 animate-pulse" />
      </div>
    )
  }

  if (!user) return <LoginScreen />

  return <>{children}</>
}

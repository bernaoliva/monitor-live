"use client"

import Image from "next/image"
import { useAuth } from "@/lib/auth-context"
import LoginScreen from "@/components/LoginScreen"

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen bg-bg flex items-center justify-center">
        <Image src="/cria-logo.png" alt="C.R.I.A" width={160} height={56} className="object-contain animate-pulse" priority />
      </div>
    )
  }

  if (!user) return <LoginScreen />

  return <>{children}</>
}

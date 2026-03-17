"use client"

import Image from "next/image"
import { useAuth } from "@/lib/auth-context"
import LoginScreen from "@/components/LoginScreen"

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen bg-bg flex items-center justify-center">
        <div className="flex items-center gap-6 animate-pulse translate-x-[18px]">
          <Image src="/cazetv-logo-branco.png" alt="CazéTV" width={90} height={32} className="object-contain" priority />
          <div className="w-px h-10 bg-white/15" />
          <Image src="/cria-logo.png" alt="C.R.I.A" width={150} height={52} className="object-contain -ml-9 translate-y-1" priority />
        </div>
      </div>
    )
  }

  if (!user) return <LoginScreen />

  return <>{children}</>
}

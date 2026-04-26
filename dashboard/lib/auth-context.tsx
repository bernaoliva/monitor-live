"use client"

import { createContext, useContext, useEffect, useState } from "react"
import {
  getAuth, onAuthStateChanged, User,
  GoogleAuthProvider, signInWithPopup, signOut,
} from "firebase/auth"
import { app } from "@/lib/firebase"

const auth = getAuth(app)

const ADMIN_EMAILS: string[] = ["admin@example.com"]

interface AuthCtx {
  user: User | null
  loading: boolean
  isAdmin: boolean
  error: string | null
  signInWithGoogle: () => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthCtx | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser]       = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)

  useEffect(() => {
    const unsub = onAuthStateChanged(auth, (u) => {
      setUser(u)
      setLoading(false)
    })
    return () => unsub()
  }, [])

  const signInWithGoogle = async () => {
    setError(null)
    const provider = new GoogleAuthProvider()
    provider.setCustomParameters({ hd: "livemode.com" })
    try {
      const result = await signInWithPopup(auth, provider)
      const email = result.user.email ?? ""
      if (!email.endsWith("@livemode.com")) {
        await signOut(auth)
        setError("Acesso restrito a contas @livemode.com")
      }
    } catch (e: unknown) {
      const code = (e as { code?: string }).code
      if (code !== "auth/popup-closed-by-user" && code !== "auth/cancelled-popup-request") {
        setError("Erro ao fazer login. Tente novamente.")
      }
    }
  }

  const logout = () => signOut(auth)

  const isAdmin = user ? ADMIN_EMAILS.includes(user.email ?? "") : false

  return (
    <AuthContext.Provider value={{ user, loading, isAdmin, error, signInWithGoogle, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}

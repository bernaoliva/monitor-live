import type { Metadata } from "next"
import "./globals.css"
import TabNav from "@/components/TabNav"
import { ChannelProvider } from "@/lib/channel-context"
import { CardLayoutProvider } from "@/lib/card-layout-context"
import ChannelSelector from "@/components/ChannelSelector"
import { AuthProvider } from "@/lib/auth-context"
import AuthGate from "@/components/AuthGate"
import CollapsibleHeader from "@/components/CollapsibleHeader"

export const metadata: Metadata = {
  title: "Monitor de Lives - CazeTV",
  description: "Dashboard de monitoramento de comentarios em tempo real",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" className="dark">
      <body className="min-h-screen bg-bg antialiased noise-bg">
        <AuthProvider>
          <AuthGate>
            <ChannelProvider>
            <CardLayoutProvider>
              <CollapsibleHeader>
                <div className="max-w-[1920px] mx-auto px-5 h-12 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    {/* Red rec dot */}
                    <div className="flex items-center gap-2">
                      <div className="relative w-2 h-2">
                        <div className="absolute inset-0 rounded-full bg-red-500 pulse-dot" />
                        <div className="absolute inset-0 rounded-full bg-red-500" />
                      </div>
                      <span className="font-bold text-[13px] text-white tracking-tight">MONITOR</span>
                    </div>
                    <div className="w-px h-5 bg-white/[0.06]" />
                    <ChannelSelector />
                    <div className="w-px h-5 bg-white/[0.06]" />
                    <TabNav />
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[10px] text-white/15 tracking-wider">v2.0</span>
                  </div>
                </div>
              </CollapsibleHeader>

              <main className="max-w-[1920px] mx-auto px-5 py-5">
                {children}
              </main>
            </CardLayoutProvider>
            </ChannelProvider>
          </AuthGate>
        </AuthProvider>
      </body>
    </html>
  )
}

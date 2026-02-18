import type { Metadata } from "next"
import "./globals.css"
import TabNav from "@/components/TabNav"

export const metadata: Metadata = {
  title: "Monitor de Lives — CazéTV",
  description: "Dashboard de monitoramento de comentários em tempo real",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" className="dark">
      <body className="min-h-screen bg-bg antialiased noise-bg">
        <header className="sticky top-0 z-50 border-b border-white/[0.04] header-glow">
          <div className="max-w-[1200px] mx-auto px-5 h-11 flex items-center justify-between">
            <div className="flex items-center gap-3">
              {/* Red rec dot */}
              <div className="flex items-center gap-2">
                <div className="relative w-2 h-2">
                  <div className="absolute inset-0 rounded-full bg-red-500 pulse-dot" />
                  <div className="absolute inset-0 rounded-full bg-red-500" />
                </div>
                <span className="font-bold text-[13px] text-white tracking-tight">MONITOR</span>
              </div>
              <div className="w-px h-4 bg-white/[0.06]" />
              <span className="text-white/25 text-[11px] font-mono tracking-wider">CAZÉTV</span>
              <div className="w-px h-4 bg-white/[0.06]" />
              <TabNav />
            </div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-[10px] text-white/15 tracking-wider">v2.0</span>
            </div>
          </div>
        </header>

        <main className="max-w-[1200px] mx-auto px-5 py-5">
          {children}
        </main>
      </body>
    </html>
  )
}

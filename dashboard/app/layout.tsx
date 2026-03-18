import type { Metadata } from "next"
import Image from "next/image"
import "./globals.css"
import TabNav from "@/components/TabNav"
import { ChannelProvider } from "@/lib/channel-context"
import { CardLayoutProvider } from "@/lib/card-layout-context"
import ChannelSelector from "@/components/ChannelSelector"
import { AuthProvider } from "@/lib/auth-context"
import AuthGate from "@/components/AuthGate"
import CollapsibleHeader from "@/components/CollapsibleHeader"

export const metadata: Metadata = {
  title: "CRIA - Monitor de Lives",
  description: "Chats em Revisão por Inteligência Artificial",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/favicon-192.png", sizes: "192x192", type: "image/png" },
    ],
    apple: "/apple-touch-icon.png",
  },
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
                <div className="max-w-[1920px] mx-auto px-5 h-12 flex items-center">
                  <div className="flex items-center gap-3 flex-1">
                    <ChannelSelector />
                    <div className="w-px h-5 bg-white/[0.06]" />
                    <TabNav />
                  </div>
                  <Image src="/cria-logo.png" alt="C.R.I.A" width={114} height={40} className="object-contain" priority />
                  <div className="flex-1" />
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

"use client"

import { useEffect, useRef, useState } from "react"

export default function CollapsibleHeader({ children }: { children: React.ReactNode }) {
  const [visible, setVisible] = useState(true)
  const lastScrollY = useRef(0)

  useEffect(() => {
    const onScroll = () => {
      const y = window.scrollY
      // Mostra se rolou para cima ou está no topo
      if (y < lastScrollY.current || y < 10) {
        setVisible(true)
      } else if (y > lastScrollY.current && y > 50) {
        setVisible(false)
      }
      lastScrollY.current = y
    }
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [])

  return (
    <header
      className={`sticky top-0 z-50 border-b border-white/[0.04] header-glow transition-transform duration-300 ${
        visible ? "translate-y-0" : "-translate-y-full"
      }`}
    >
      {children}
    </header>
  )
}

"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { Radio, History } from "lucide-react"

const tabs = [
  { href: "/", label: "AO VIVO", icon: Radio },
  { href: "/historico", label: "HISTORICO", icon: History },
] as const

export default function TabNav() {
  const pathname = usePathname()

  return (
    <div className="flex gap-0.5 bg-white/[0.03] p-0.5 rounded">
      {tabs.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href)
        return (
          <Link
            key={href}
            href={href}
            className={`flex items-center gap-1.5 px-2.5 py-1 text-[10px] font-bold rounded transition-all font-mono tracking-wider ${
              active
                ? "bg-white/[0.08] text-white/70"
                : "text-white/30 hover:text-white/50"
            }`}
          >
            <Icon size={10} />
            {label}
          </Link>
        )
      })}
    </div>
  )
}

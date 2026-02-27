"use client"

import Image from "next/image"
import { useChannels } from "@/lib/channel-context"

export default function ChannelSelector() {
  const { selected, toggle } = useChannels()

  return (
    <div className="flex items-center gap-4">
      <button
        onClick={() => toggle("CAZETV")}
        title="CazeTV"
        className={`transition-all ${selected.CAZETV ? "opacity-100" : "opacity-35 hover:opacity-65"}`}
      >
        <Image
          src="/cazetv-logo-branco.png"
          alt="CazeTV"
          width={100}
          height={28}
          className="h-[26px] w-auto object-contain"
        />
        <span className={`block mt-0.5 h-0.5 rounded-full transition-all ${selected.CAZETV ? "bg-white/60" : "bg-transparent"}`} />
      </button>

      <button
        onClick={() => toggle("GETV")}
        title="ge.tv"
        className={`transition-all ${selected.GETV ? "opacity-100" : "opacity-35 hover:opacity-65"}`}
      >
        <Image
          src="/getv-logo.png"
          alt="ge.tv"
          width={90}
          height={26}
          className="h-[24px] w-auto object-contain"
        />
        <span className={`block mt-0.5 h-0.5 rounded-full transition-all ${selected.GETV ? "bg-emerald-400/80" : "bg-transparent"}`} />
      </button>
    </div>
  )
}

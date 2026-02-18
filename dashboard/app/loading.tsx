export default function Loading() {
  return (
    <div className="space-y-10 animate-pulse">
      {/* Header skeleton */}
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <div className="h-7 w-32 bg-white/5 rounded-lg" />
          <div className="h-4 w-64 bg-white/5 rounded-lg" />
        </div>
        <div className="h-8 w-28 bg-white/5 rounded-full" />
      </div>

      {/* Stats skeleton */}
      <div className="grid grid-cols-3 gap-4">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="bg-surface border border-white/[0.06] rounded-2xl p-5 space-y-2">
            <div className="h-3 w-24 bg-white/5 rounded" />
            <div className="h-8 w-16 bg-white/5 rounded" />
          </div>
        ))}
      </div>

      {/* Cards skeleton */}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="bg-surface border border-white/[0.06] rounded-2xl p-5 space-y-4">
            <div className="h-4 w-20 bg-white/5 rounded" />
            <div className="h-5 w-full bg-white/5 rounded" />
            <div className="h-5 w-3/4 bg-white/5 rounded" />
            <div className="grid grid-cols-2 gap-2">
              <div className="h-16 bg-white/5 rounded-xl" />
              <div className="h-16 bg-white/5 rounded-xl" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

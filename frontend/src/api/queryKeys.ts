export const queryKeys = {
  bootstrap: ["bootstrap"] as const,
  event: ["event"] as const,
  phases: ["event-phases"] as const,
  guessAvailability: ["guess-availability"] as const,
  songs: {
    mine: ["songs", "mine"] as const,
    admin: ["songs", "admin"] as const,
  },
  draws: {
    mine: ["draws", "mine"] as const,
    admin: ["draws", "admin"] as const,
    stats: ["draws", "stats"] as const,
  },
  submissions: {
    targets: ["submissions", "targets"] as const,
    mine: ["submissions", "mine"] as const,
    jobs: ["submissions", "jobs"] as const,
    admin: (tracks: string, limit: number, offset: number) => ["submissions", "admin", tracks, limit, offset] as const,
    adminJobs: ["submissions", "admin-jobs"] as const,
  },
  guess: {
    charts: ["guess", "charts"] as const,
    designer: ["guess", "designer"] as const,
    quota: ["guess", "quota"] as const,
    adminCharts: ["guess", "admin-charts"] as const,
    issues: ["guess", "issues"] as const,
    candidates: ["guess", "candidates"] as const,
    stats: (scope: string) => ["guess", "stats", scope] as const,
    details: (scope: string, offset: number) => ["guess", "details", scope, offset] as const,
  },
  admin: {
    users: ["admin", "users"] as const,
    overview: ["admin", "overview"] as const,
    banImports: ["admin", "ban-imports"] as const,
    swapAudit: ["admin", "swap-audit"] as const,
  },
  swap: ["swap", "mine"] as const,
} as const;

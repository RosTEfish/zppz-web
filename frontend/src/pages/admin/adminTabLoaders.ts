export const adminTabLoaders = {
  overview: () => import("./AdminOverview"),
  settings: () => import("./AdminSettings"),
  users: () => import("./AdminUsers"),
  songs: () => import("./AdminSongs"),
  draw: () => import("./AdminDraw"),
  phases: () => import("./AdminPhasesAndSwap"),
  submissions: () => import("./AdminSubmissions"),
  guess: () => import("./AdminGuess"),
  stats: () => import("./AdminStats"),
  banlist: () => import("./AdminBanlist"),
  webhooks: () => import("./AdminWebhooks"),
};

export type AdminTab = keyof typeof adminTabLoaders;

export function preloadAdminTab(pathname: string): Promise<unknown> {
  const requested = pathname.match(/^\/admin\/([^/]+)/)?.[1] as AdminTab | undefined;
  return adminTabLoaders[requested && requested in adminTabLoaders ? requested : "overview"]();
}

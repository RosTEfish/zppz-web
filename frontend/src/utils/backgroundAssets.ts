export type BackgroundRole = "banner" | "post" | "square";

export interface BackgroundAsset {
  file_name: string;
  url: string;
}

export interface ResolvedBackgrounds {
  banner: BackgroundAsset | null;
  post: BackgroundAsset | null;
  square: BackgroundAsset | null;
  /** Best visual for the home hero: banner, else post, else square. */
  hero: BackgroundAsset | null;
  /** Best visual for auth / compact brand surfaces: square, else post. */
  brand: BackgroundAsset | null;
}

const ROLES: BackgroundRole[] = ["banner", "post", "square"];

export function parseBackgroundRole(fileName: string): { role: BackgroundRole | null; editionKey: string | null } {
  const stem = fileName.replace(/\.[^.]+$/, "").toLowerCase();
  const role = ROLES.find((item) => stem === item || stem.endsWith(`_${item}`)) ?? null;
  if (!role) return { role: null, editionKey: null };
  if (stem === role) return { role, editionKey: null };
  return { role, editionKey: stem.slice(0, -(role.length + 1)) };
}

/** Derive preferred edition keys from the current event name/slug (most specific first). */
export function preferredEditionKeys(event: { name?: string | null; slug?: string | null } | null | undefined): string[] {
  const keys: string[] = [];
  const slug = (event?.slug || "").trim().toLowerCase();
  const name = event?.name || "";

  if (slug) {
    keys.push(slug);
    const slugEdition = slug.match(/zppz[-_]?(\d+)/i);
    if (slugEdition) keys.push(`zppz${slugEdition[1]}`);
  }

  const nameEdition = name.match(/#\s*(\d+)/);
  if (nameEdition) keys.push(`zppz${nameEdition[1]}`);

  return [...new Set(keys.filter(Boolean))];
}

function pickForRole(assets: BackgroundAsset[], role: BackgroundRole, preferredKeys: string[]): BackgroundAsset | null {
  const candidates = assets
    .map((asset) => ({ asset, ...parseBackgroundRole(asset.file_name) }))
    .filter((item) => item.role === role);

  for (const key of preferredKeys) {
    const match = candidates.find((item) => item.editionKey === key);
    if (match) return match.asset;
  }

  const canonical = candidates.find((item) => item.editionKey === null);
  if (canonical) return canonical.asset;

  return candidates[0]?.asset ?? null;
}

export function resolveBackgrounds(
  assets: BackgroundAsset[] | null | undefined,
  event?: { name?: string | null; slug?: string | null } | null,
): ResolvedBackgrounds {
  const list = Array.isArray(assets) ? assets : [];
  const preferredKeys = preferredEditionKeys(event);
  const banner = pickForRole(list, "banner", preferredKeys);
  const post = pickForRole(list, "post", preferredKeys);
  const square = pickForRole(list, "square", preferredKeys);
  return {
    banner,
    post,
    square,
    hero: banner ?? post ?? square,
    brand: square ?? post ?? banner,
  };
}

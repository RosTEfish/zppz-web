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
  /** Higher-res companion for large viewports (usually post when hero is banner). */
  heroLarge: BackgroundAsset | null;
  /** Best visual for auth / compact brand surfaces: square, else post. */
  brand: BackgroundAsset | null;
  /** Small square mark for AppBar/drawer (prefers generated `.thumb.webp`). */
  brandMark: BackgroundAsset | null;
}

const ROLES: BackgroundRole[] = ["banner", "post", "square"];
const FORMAT_RANK: Record<string, number> = {
  ".webp": 0,
  ".jpg": 1,
  ".jpeg": 2,
  ".png": 3,
  ".gif": 4,
};

function extensionOf(fileName: string): string {
  const idx = fileName.lastIndexOf(".");
  return idx >= 0 ? fileName.slice(idx).toLowerCase() : "";
}

function formatRank(fileName: string): number {
  return FORMAT_RANK[extensionOf(fileName)] ?? 50;
}

/** Skip derived thumbs when resolving role art. */
export function isThumbAsset(fileName: string): boolean {
  return /\.thumb\./i.test(fileName) || /_thumb\./i.test(fileName);
}

export function parseBackgroundRole(fileName: string): { role: BackgroundRole | null; editionKey: string | null } {
  if (isThumbAsset(fileName)) return { role: null, editionKey: null };
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

function bestAsset(candidates: BackgroundAsset[]): BackgroundAsset | null {
  if (!candidates.length) return null;
  return [...candidates].sort((a, b) => formatRank(a.file_name) - formatRank(b.file_name))[0] ?? null;
}

function pickForRole(assets: BackgroundAsset[], role: BackgroundRole, preferredKeys: string[]): BackgroundAsset | null {
  const candidates = assets
    .map((asset) => ({ asset, ...parseBackgroundRole(asset.file_name) }))
    .filter((item) => item.role === role);

  for (const key of preferredKeys) {
    const match = bestAsset(candidates.filter((item) => item.editionKey === key).map((item) => item.asset));
    if (match) return match;
  }

  const canonical = bestAsset(candidates.filter((item) => item.editionKey === null).map((item) => item.asset));
  if (canonical) return canonical;

  return bestAsset(candidates.map((item) => item.asset));
}

function thumbNameFor(fileName: string): string {
  return fileName.replace(/(\.[^.]+)$/, ".thumb$1");
}

function resolveBrandMark(assets: BackgroundAsset[], brand: BackgroundAsset | null): BackgroundAsset | null {
  if (!brand) return null;
  const thumb = assets.find((asset) => asset.file_name === thumbNameFor(brand.file_name));
  return thumb ?? brand;
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
  const hero = banner ?? post ?? square;
  const heroLarge = post && hero && post.url !== hero.url ? post : null;
  const brand = square ?? post ?? banner;
  return {
    banner,
    post,
    square,
    hero,
    heroLarge,
    brand,
    brandMark: resolveBrandMark(list, brand),
  };
}

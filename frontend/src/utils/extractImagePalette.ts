import {
  accessibleBrandFromSample,
  clamp,
  hexToRgb,
  hslToRgb,
  mixRgb,
  rgbaString,
  rgbToHex,
  rgbToHsl,
  type RGB,
} from "./colorMath";

export interface EventPalette {
  main: string;
  dark: string;
  darker: string;
  tint: string;
  wash: string;
  accent: string;
  accentSoft: string;
  washA: string;
  washB: string;
  washC: string;
  selection: string;
  shadowInk: RGB;
}

export const defaultEventPalette: EventPalette = {
  main: "#176B52",
  dark: "#0E523E",
  darker: "#0A3B2D",
  tint: "#DCEEE5",
  wash: "rgba(23, 107, 82, 0.06)",
  accent: "#C9973B",
  accentSoft: "rgba(201, 151, 59, 0.14)",
  washA: "rgba(23, 107, 82, 0.07)",
  washB: "rgba(31, 110, 128, 0.05)",
  washC: "rgba(201, 151, 59, 0.04)",
  selection: "rgba(23, 107, 82, 0.18)",
  shadowInk: { r: 13, g: 53, b: 41 },
};

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.decoding = "async";
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error(`Failed to load image: ${url}`));
    image.src = url;
  });
}

function sampleDominantColor(image: HTMLImageElement): RGB | null {
  const size = 48;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;
  ctx.drawImage(image, 0, 0, size, size);
  const { data } = ctx.getImageData(0, 0, size, size);

  type Bucket = { count: number; weight: number; r: number; g: number; b: number };
  const buckets = new Map<string, Bucket>();

  for (let i = 0; i < data.length; i += 4) {
    const alpha = data[i + 3];
    if (alpha < 200) continue;
    const rgb = { r: data[i], g: data[i + 1], b: data[i + 2] };
    const hsl = rgbToHsl(rgb);
    // Skip near-white / near-black / gray UI chrome in artwork.
    if (hsl.l > 92 || hsl.l < 12 || hsl.s < 18) continue;
    const key = `${Math.round(hsl.h / 12) * 12}:${Math.round(hsl.s / 12) * 12}`;
    const vibrance = (hsl.s / 100) * (1 - Math.abs(hsl.l - 52) / 52);
    const current = buckets.get(key) ?? { count: 0, weight: 0, r: 0, g: 0, b: 0 };
    current.count += 1;
    current.weight += vibrance;
    current.r += rgb.r * vibrance;
    current.g += rgb.g * vibrance;
    current.b += rgb.b * vibrance;
    buckets.set(key, current);
  }

  let best: Bucket | null = null;
  for (const bucket of buckets.values()) {
    if (!best || bucket.weight > best.weight) best = bucket;
  }
  if (!best || best.weight <= 0) return null;
  return {
    r: best.r / best.weight,
    g: best.g / best.weight,
    b: best.b / best.weight,
  };
}

export function paletteFromSample(sample: RGB): EventPalette {
  const accentHsl = rgbToHsl(sample);
  const accent = hslToRgb({
    h: accentHsl.h,
    s: clamp(accentHsl.s, 55, 90),
    l: clamp(accentHsl.l, 48, 62),
  });
  const main = accessibleBrandFromSample(sample);
  const mainHsl = rgbToHsl(main);
  const dark = hslToRgb({ h: mainHsl.h, s: clamp(mainHsl.s + 4, 40, 75), l: clamp(mainHsl.l - 8, 16, 36) });
  const darker = hslToRgb({ h: mainHsl.h, s: clamp(mainHsl.s + 6, 40, 78), l: clamp(mainHsl.l - 14, 10, 28) });
  const tint = mixRgb(hslToRgb({ h: mainHsl.h, s: clamp(mainHsl.s * 0.35, 12, 28), l: 93 }), { r: 255, g: 255, b: 255 }, 0.15);
  const softAccent = hslToRgb({
    h: (accentHsl.h + 28) % 360,
    s: clamp(accentHsl.s * 0.55, 35, 70),
    l: clamp(accentHsl.l + 6, 50, 68),
  });
  const shadowInk = mixRgb(darker, { r: 18, g: 42, b: 33 }, 0.35);

  return {
    main: rgbToHex(main),
    dark: rgbToHex(dark),
    darker: rgbToHex(darker),
    tint: rgbToHex(tint),
    wash: rgbaString(main, 0.06),
    accent: rgbToHex(accent),
    accentSoft: rgbaString(accent, 0.14),
    washA: rgbaString(main, 0.08),
    washB: rgbaString(softAccent, 0.06),
    washC: rgbaString(accent, 0.05),
    selection: rgbaString(main, 0.18),
    shadowInk,
  };
}

export async function extractImagePalette(url: string): Promise<EventPalette> {
  const image = await loadImage(url);
  const sample = sampleDominantColor(image);
  if (!sample) return defaultEventPalette;
  return paletteFromSample(sample);
}

export function applyPaletteCssVars(palette: EventPalette, target: HTMLElement = document.documentElement) {
  target.style.setProperty("--zppz-brand", palette.main);
  target.style.setProperty("--zppz-brand-dark", palette.dark);
  target.style.setProperty("--zppz-brand-darker", palette.darker);
  target.style.setProperty("--zppz-brand-tint", palette.tint);
  target.style.setProperty("--zppz-brand-wash", palette.wash);
  target.style.setProperty("--zppz-accent", palette.accent);
  target.style.setProperty("--zppz-accent-soft", palette.accentSoft);
  target.style.setProperty("--zppz-wash-a", palette.washA);
  target.style.setProperty("--zppz-wash-b", palette.washB);
  target.style.setProperty("--zppz-wash-c", palette.washC);
  target.style.setProperty("--zppz-selection", palette.selection);
}

export function clearPaletteCssVars(target: HTMLElement = document.documentElement) {
  [
    "--zppz-brand",
    "--zppz-brand-dark",
    "--zppz-brand-darker",
    "--zppz-brand-tint",
    "--zppz-brand-wash",
    "--zppz-accent",
    "--zppz-accent-soft",
    "--zppz-wash-a",
    "--zppz-wash-b",
    "--zppz-wash-c",
    "--zppz-selection",
  ].forEach((key) => target.style.removeProperty(key));
}

/** Test helper: build palette from a hex sample without canvas. */
export function paletteFromHex(hex: string): EventPalette {
  return paletteFromSample(hexToRgb(hex));
}

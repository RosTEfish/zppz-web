import { hexToRgb, rgbaString } from "../utils/colorMath";
import type { EventPalette } from "../utils/extractImagePalette";

/** Difficulty slot (1-7) extracted from source_level_slot for compact visual coding. */
export function getChartLevelSlot(sourceLevelSlot?: string): string {
  return /(?:lv_)?([1-7])$/i.exec(sourceLevelSlot?.trim() ?? "")?.[1] ?? "";
}

/** Difficulty encoded as brand intensity; the card body stays on paper. */
export function chartLevelAccent(levelSlot: string, palette: EventPalette): string | undefined {
  const slot = Number(levelSlot);
  if (!Number.isInteger(slot) || slot < 1 || slot > 7) return undefined;
  const alpha = 0.16 + (slot - 1) * 0.07;
  return rgbaString(hexToRgb(palette.main), alpha);
}

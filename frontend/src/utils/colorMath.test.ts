import { describe, expect, it } from "vitest";
import { accessibleBrandFromSample, contrastRatio, hexToRgb, rgbToHex } from "./colorMath";
import { paletteFromHex } from "./extractImagePalette";

describe("accessibleBrandFromSample", () => {
  it("darkens a bright coral sample into an accessible primary", () => {
    const sample = hexToRgb("#FF6B4A");
    const brand = accessibleBrandFromSample(sample);
    expect(contrastRatio(brand, { r: 255, g: 255, b: 255 })).toBeGreaterThanOrEqual(4.5);
    expect(rgbToHex(brand)).not.toBe("#FF6B4A");
  });
});

describe("paletteFromHex", () => {
  it("produces brand and accent tokens from an orange sample", () => {
    const palette = paletteFromHex("#FF7A45");
    expect(palette.main).toMatch(/^#[0-9A-F]{6}$/);
    expect(palette.accent).toMatch(/^#[0-9A-F]{6}$/);
    expect(palette.wash).toContain("rgba(");
    expect(contrastRatio(hexToRgb(palette.main), { r: 255, g: 255, b: 255 })).toBeGreaterThanOrEqual(4.5);
  });

  it("produces a green-leaning palette from a lime sample", () => {
    const palette = paletteFromHex("#B6E54A");
    const rgb = hexToRgb(palette.main);
    // Green channel should dominate for a lime-derived brand.
    expect(rgb.g).toBeGreaterThan(rgb.r);
    expect(rgb.g).toBeGreaterThan(rgb.b);
  });
});

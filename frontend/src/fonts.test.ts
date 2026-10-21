import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { fontDisplay, fontSans } from "./theme";

const fontsCss = readFileSync(resolve(import.meta.dirname, "fonts.css"), "utf8");

function fontImports(css: string): string[] {
  return [...css.matchAll(/@import\s+"([^"]+)"/g)].map((match) => match[1]);
}

describe("font loading contract", () => {
  it("does not download Noto Sans SC webfonts for body text", () => {
    expect(fontsCss).not.toMatch(/noto-sans-sc/);
    expect(fontImports(fontsCss).some((item) => item.includes("noto-sans"))).toBe(false);
  });

  it("keeps a single Noto Serif SC weight for headings", () => {
    expect(fontImports(fontsCss)).toEqual([
      "@fontsource/outfit/400.css",
      "@fontsource/outfit/600.css",
      "@fontsource/outfit/700.css",
      "@fontsource/noto-serif-sc/chinese-simplified-700.css",
    ]);
  });

  it("uses a system Chinese sans stack for body text and serif fallbacks for headings", () => {
    expect(fontSans.startsWith('"Outfit"')).toBe(true);
    expect(fontSans).toContain("PingFang SC");
    expect(fontSans).toContain("Microsoft YaHei");
    expect(fontSans).toContain("Noto Sans CJK SC");
    expect(fontDisplay.startsWith('"Noto Serif SC"')).toBe(true);
    expect(fontDisplay).toContain("Songti SC");
    expect(fontDisplay).toContain("Noto Serif CJK SC");
    expect(fontDisplay).not.toContain("Noto Sans SC");
  });
});

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { pathFromTo, viewTransitionKind } from "./viewTransition";

const indexCss = readFileSync(resolve(import.meta.dirname, "../index.css"), "utf8");

describe("viewTransitionKind", () => {
  it("detects auth shell transitions", () => {
    expect(viewTransitionKind("/login", "/")).toBe("to-auth");
    expect(viewTransitionKind("/login?next=/", "/songs")).toBe("to-auth");
    expect(viewTransitionKind("/", "/login")).toBe("to-app");
    expect(viewTransitionKind("/songs", "/login")).toBe("to-app");
  });

  it("uses page transitions inside the app shell", () => {
    expect(viewTransitionKind("/songs", "/")).toBe("to-page");
    expect(viewTransitionKind("/draw", "/songs")).toBe("to-page");
    expect(viewTransitionKind("/admin/overview", "/account")).toBe("to-page");
    expect(viewTransitionKind("/login", "/login")).toBe("to-page");
  });
});

describe("mobile in-app page switch", () => {
  it("covers the outgoing snapshot instead of stacking it under the incoming page", () => {
    const mobileStart = indexCss.indexOf("/* mobile-page-switch");
    expect(mobileStart).toBeGreaterThan(-1);
    const mobile = indexCss.slice(mobileStart, indexCss.indexOf("@media (max-width: 599px)", mobileStart));

    expect(mobile).toContain("@media (max-width: 899.95px)");
    expect(mobile).toContain('html[data-vt="to-page"]::view-transition-group(zppz-page)');
    expect(mobile).toContain("animation: none");
    expect(mobile).toContain("overflow: clip");
    expect(mobile).toContain("background-color: #fafbfa");
    expect(mobile).toMatch(/::view-transition-old\(zppz-page\)\s*\{[^}]*opacity:\s*0/);
    expect(mobile).toContain("animation: zppz-page-cover 280ms cubic-bezier(0.32, 0.72, 0, 1) both");

    const cover = indexCss.match(/@keyframes zppz-page-cover\s*\{([\s\S]*?)\n\}/)?.[1] ?? "";
    expect(cover).toContain("transform: translateY(12px)");
    expect(cover).not.toContain("opacity");

    const desktopOld = indexCss.slice(0, mobileStart);
    expect(desktopOld).toContain('html[data-vt="to-page"]::view-transition-old(zppz-page)');
    expect(desktopOld).toContain("animation: zppz-page-out 220ms cubic-bezier(0.32, 0.72, 0, 1) both");
    expect(desktopOld).toContain("animation: zppz-page-in 300ms cubic-bezier(0.32, 0.72, 0, 1) both");
  });
});

describe("pathFromTo", () => {
  it("strips query and hash from string targets", () => {
    expect(pathFromTo("/songs?view=ban-check#top")).toBe("/songs");
  });

  it("reads pathname from location objects", () => {
    expect(pathFromTo({ pathname: "/archive", search: "?q=1" })).toBe("/archive");
    expect(pathFromTo({})).toBe("/");
  });
});

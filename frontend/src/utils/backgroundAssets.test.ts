import { describe, expect, it } from "vitest";
import {
  parseBackgroundRole,
  preferredEditionKeys,
  resolveBackgrounds,
  type BackgroundAsset,
} from "./backgroundAssets";

const sample: BackgroundAsset[] = [
  { file_name: "banner.webp", url: "/api/v1/assets/backgrounds/banner.webp" },
  { file_name: "post.webp", url: "/api/v1/assets/backgrounds/post.webp" },
  { file_name: "square.webp", url: "/api/v1/assets/backgrounds/square.webp" },
  { file_name: "zppz4_post.webp", url: "/api/v1/assets/backgrounds/zppz4_post.webp" },
  { file_name: "zppz4_square.webp", url: "/api/v1/assets/backgrounds/zppz4_square.webp" },
];

describe("parseBackgroundRole", () => {
  it("parses canonical and edition-prefixed roles", () => {
    expect(parseBackgroundRole("banner.webp")).toEqual({ role: "banner", editionKey: null });
    expect(parseBackgroundRole("zppz4_post.WEBP")).toEqual({ role: "post", editionKey: "zppz4" });
    expect(parseBackgroundRole("readme.txt")).toEqual({ role: null, editionKey: null });
  });
});

describe("preferredEditionKeys", () => {
  it("derives keys from slug and event name", () => {
    expect(preferredEditionKeys({ name: "这谱谱这 #5", slug: "zppz-current" })).toEqual(["zppz-current", "zppz5"]);
    expect(preferredEditionKeys({ name: "Battle", slug: "zppz4" })).toEqual(["zppz4"]);
  });
});

describe("resolveBackgrounds", () => {
  it("prefers canonical assets for the current #5 event", () => {
    const resolved = resolveBackgrounds(sample, { name: "这谱谱这 #5", slug: "zppz-current" });
    expect(resolved.banner?.file_name).toBe("banner.webp");
    expect(resolved.post?.file_name).toBe("post.webp");
    expect(resolved.square?.file_name).toBe("square.webp");
    expect(resolved.hero?.file_name).toBe("banner.webp");
    expect(resolved.brand?.file_name).toBe("square.webp");
  });

  it("prefers edition-prefixed assets when the event matches", () => {
    const resolved = resolveBackgrounds(sample, { name: "这谱谱这 #4", slug: "zppz4" });
    expect(resolved.post?.file_name).toBe("zppz4_post.webp");
    expect(resolved.square?.file_name).toBe("zppz4_square.webp");
    expect(resolved.banner?.file_name).toBe("banner.webp");
    expect(resolved.hero?.file_name).toBe("banner.webp");
    expect(resolved.brand?.file_name).toBe("zppz4_square.webp");
  });

  it("prefers webp over png for the same role", () => {
    const mixed: BackgroundAsset[] = [
      { file_name: "banner.png", url: "/api/v1/assets/backgrounds/banner.png" },
      { file_name: "banner.webp", url: "/api/v1/assets/backgrounds/banner.webp" },
    ];
    expect(resolveBackgrounds(mixed, { name: "x", slug: "y" }).banner?.file_name).toBe("banner.webp");
  });

  it("falls back gracefully with empty input", () => {
    expect(resolveBackgrounds([], { name: "x", slug: "y" })).toEqual({
      banner: null,
      post: null,
      square: null,
      hero: null,
      brand: null,
    });
  });
});

import { describe, expect, it } from "vitest";
import {
  parseBackgroundRole,
  preferredEditionKeys,
  resolveBackgrounds,
  type BackgroundAsset,
} from "./backgroundAssets";

const sample: BackgroundAsset[] = [
  { file_name: "banner.png", url: "/api/v1/assets/backgrounds/banner.png" },
  { file_name: "post.png", url: "/api/v1/assets/backgrounds/post.png" },
  { file_name: "square.png", url: "/api/v1/assets/backgrounds/square.png" },
  { file_name: "zppz4_post.png", url: "/api/v1/assets/backgrounds/zppz4_post.png" },
  { file_name: "zppz4_square.png", url: "/api/v1/assets/backgrounds/zppz4_square.png" },
];

describe("parseBackgroundRole", () => {
  it("parses canonical and edition-prefixed roles", () => {
    expect(parseBackgroundRole("banner.png")).toEqual({ role: "banner", editionKey: null });
    expect(parseBackgroundRole("zppz4_post.PNG")).toEqual({ role: "post", editionKey: "zppz4" });
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
    expect(resolved.banner?.file_name).toBe("banner.png");
    expect(resolved.post?.file_name).toBe("post.png");
    expect(resolved.square?.file_name).toBe("square.png");
    expect(resolved.hero?.file_name).toBe("banner.png");
    expect(resolved.brand?.file_name).toBe("square.png");
  });

  it("prefers edition-prefixed assets when the event matches", () => {
    const resolved = resolveBackgrounds(sample, { name: "这谱谱这 #4", slug: "zppz4" });
    expect(resolved.post?.file_name).toBe("zppz4_post.png");
    expect(resolved.square?.file_name).toBe("zppz4_square.png");
    expect(resolved.banner?.file_name).toBe("banner.png");
    expect(resolved.hero?.file_name).toBe("banner.png");
    expect(resolved.brand?.file_name).toBe("zppz4_square.png");
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

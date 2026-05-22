import { describe, expect, it } from "vitest";
import { formatMB, formatTime } from "./v1";

describe("v1 API helpers", () => {
  it("formats file sizes", () => {
    expect(formatMB(1024 * 1024)).toBe("1.00 MB");
  });

  it("handles empty timestamps", () => {
    expect(formatTime(null)).toBe("未设置");
  });
});

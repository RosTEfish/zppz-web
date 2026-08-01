import { describe, expect, it } from "vitest";
import dayjs from "dayjs";
import { BUSINESS_TIMEZONE, toBusinessTime, toUtcIso } from "./phaseDateTime";

describe("phase date-time conversion", () => {
  it("displays UTC values in Beijing time", () => {
    expect(toBusinessTime("2026-08-01T00:30:00Z")?.format("YYYY-MM-DD HH:mm")).toBe("2026-08-01 08:30");
  });

  it("submits Beijing wall time as UTC ISO", () => {
    expect(toUtcIso(dayjs.tz("2026-08-01 08:30", BUSINESS_TIMEZONE))).toBe("2026-08-01T00:30:00.000Z");
  });
});

import { describe, expect, it } from "vitest";
import { pathFromTo, viewTransitionKind } from "./viewTransition";

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

describe("pathFromTo", () => {
  it("strips query and hash from string targets", () => {
    expect(pathFromTo("/songs?view=ban-check#top")).toBe("/songs");
  });

  it("reads pathname from location objects", () => {
    expect(pathFromTo({ pathname: "/archive", search: "?q=1" })).toBe("/archive");
    expect(pathFromTo({})).toBe("/");
  });
});

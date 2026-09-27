import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ConfirmProvider } from "material-ui-confirm";
import { SWRConfig } from "swr";
import { afterEach, describe, expect, it } from "vitest";
import { mockApi } from "../../testServer";
import AdminGuess from "./AdminGuess";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

const chart = {
  id: 31,
  title: "低难度谱面",
  author: "曲师",
  designer: "谱师",
  level: "13+",
  lane: "normal",
  guess_group_key: "group-31",
  source_submission_type: "normal",
  source_submission_id: 31,
  source_level_slot: "4",
  cover_path: "",
  storage_path: "",
  is_self_selected: false,
  plays: 0,
  created_at: "2026-07-04T00:00:00",
  love_votes: 0,
  funny_votes: 0,
  my_votes: [],
  love_vote_bucket: "below_14",
  love_vote_bucket_auto: "below_14",
  love_vote_bucket_override: null,
};

describe("AdminGuess", () => {
  afterEach(() => cleanup());

  it("saves a manual true-love bucket for one chart", async () => {
    const updates: unknown[] = [];
    mockApi((url, init) => {
      const path = new URL(url).pathname;
      if (path.includes("/admin/guess-game/charts/") && init.method === "PUT") {
        const payload = JSON.parse(String(init.body));
        updates.push(payload);
        return json({ ...chart, love_vote_bucket: "at_least_14", love_vote_bucket_override: "at_least_14" });
      }
      if (path.endsWith("/admin/guess-game/charts")) return json([chart]);
      if (path.endsWith("/admin/guess-game/import-issues")) return json([]);
      if (path.endsWith("/admin/guess-game/author-candidates")) return json([]);
      return json({ detail: "not found" }, 404);
    });

    render(
      <SWRConfig value={{ provider: () => new Map(), shouldRetryOnError: false }}>
        <ConfirmProvider><AdminGuess /></ConfirmProvider>
      </SWRConfig>,
    );

    const bucket = await screen.findByRole("combobox", { name: "真爱票分类 低难度谱面 13+" });
    expect(bucket).toHaveTextContent("跟随等级（14 以下）");
    fireEvent.mouseDown(bucket);
    fireEvent.click(await screen.findByRole("option", { name: "14 及以上" }));

    await waitFor(() => expect(updates).toEqual([expect.objectContaining({
      title: "低难度谱面",
      level: "13+",
      love_vote_bucket_override: "at_least_14",
    })]));
    expect(await screen.findByText("已更新《低难度谱面》13+ 的真爱票分类")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "真爱票分类 低难度谱面 13+" })).toHaveTextContent("14 及以上");
  });
});

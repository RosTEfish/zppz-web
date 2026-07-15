import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/v1";
import { BanCheckPanel, canSubmitWithBanCheck, useBanCheck } from "./BanCheckPanel";


function Harness() {
  const state = useBanCheck("Ban Sng", "Artist");
  return <><BanCheckPanel state={state} /><button disabled={!canSubmitWithBanCheck(state)}>继续</button></>;
}


describe("BanCheckPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows a review warning and requires explicit confirmation", async () => {
    vi.spyOn(api, "checkBan").mockResolvedValue({
      status: "review",
      import_id: 1,
      matches: [{ entry_id: 7, title: "Ban Song", artist: "Artist", round: "#1 - Pure", note: "", match_type: "fuzzy", score: 96.2, reason: "曲名相似" }],
    });

    render(<Harness />);
    await waitFor(() => expect(screen.getByText("疑似命中往届 Ban 曲，请人工确认")).toBeInTheDocument(), { timeout: 1500 });
    expect(screen.getByRole("button", { name: "继续" })).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: "我已核对上述记录，确认这不是同一首曲目" }));
    expect(screen.getByRole("button", { name: "继续" })).toBeEnabled();
  });
});

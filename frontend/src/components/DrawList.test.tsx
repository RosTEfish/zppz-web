import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { DrawAssignmentRead } from "../api/v1";
import { DrawList } from "./DrawList";

const rows = [{
  id: 1,
  assigned_to: { id: 20, user_code: "assignee-id", display_name: "参赛者", roles: [], identity: "participant" },
  song: {
    id: 10,
    song_name: "测试曲目",
    artist: "测试曲师",
    song_type: "A",
    remark: "请使用完整版音源",
    submitter: { id: 30, user_code: "submitter-id", display_name: "投稿人姓名", roles: [], identity: "audience" },
    created_at: "2026-08-02T00:00:00Z",
  },
  created_at: "2026-08-02T01:00:00Z",
}] as DrawAssignmentRead[];

describe("DrawList", () => {
  afterEach(cleanup);

  it("shows the song remark without exposing the submitter", () => {
    render(<DrawList rows={rows} showAssignee={false} />);

    expect(screen.getByRole("columnheader", { name: "备注" })).toBeInTheDocument();
    expect(screen.getByText("请使用完整版音源")).toBeInTheDocument();
    expect(screen.queryByText("投稿人", { exact: false })).not.toBeInTheDocument();
    expect(screen.queryByText("submitter-id")).not.toBeInTheDocument();
    expect(screen.queryByText("投稿人姓名")).not.toBeInTheDocument();
  });
});

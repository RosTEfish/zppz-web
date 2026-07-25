import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { SubmissionProcessingJob, SubmissionUploadOptions } from "../api/v1";
import { useSubmissionUploadDialog } from "./SubmissionUploadDialog";

const QUEUED_JOB: SubmissionProcessingJob = {
  id: "job-1",
  intent_id: "intent-1",
  status: "queued",
  stage: "uploaded",
  message: "压缩包已上传，等待后台校验",
  file_name: "chart.zip",
  file_size: 3,
  source_song_id: 7,
  replace_submission_id: null,
  submission: null,
  created_at: "2026-07-26T00:00:00Z",
  updated_at: "2026-07-26T00:00:00Z",
};

function Harness({
  starter,
  onQueued = vi.fn(),
}: {
  starter: (options: SubmissionUploadOptions) => Promise<SubmissionProcessingJob>;
  onQueued?: (job: SubmissionProcessingJob) => void;
}) {
  const upload = useSubmissionUploadDialog(onQueued);
  return (
    <>
      <button onClick={() => void upload.start(new File(["zip"], "chart.zip"), starter)}>
        上传
      </button>
      {upload.dialog}
    </>
  );
}

describe("SubmissionUploadDialog", () => {
  it("switches to the durable background-processing acknowledgement after enqueue", async () => {
    const onQueued = vi.fn();
    const starter = vi.fn(async (options: SubmissionUploadOptions) => {
      options.onProgress?.({
        phase: "uploading",
        loaded: 2,
        total: 3,
        percent: 66.7,
        bytesPerSecond: 1024,
        etaSeconds: 1,
      });
      options.onProgress?.({
        phase: "confirming",
        loaded: 3,
        total: 3,
        percent: 100,
        bytesPerSecond: 0,
        etaSeconds: null,
      });
      return QUEUED_JOB;
    });
    render(<Harness starter={starter} onQueued={onQueued} />);

    fireEvent.click(screen.getByRole("button", { name: "上传" }));

    expect(await screen.findByRole("heading", { name: /压缩包上传成功/ })).toBeInTheDocument();
    expect(screen.getByText(/服务器会在后台继续校验谱面/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "知道了" })).toBeEnabled();
    expect(onQueued).toHaveBeenCalledWith(QUEUED_JOB);
  });

  it("makes cancellation abortable only before R2 confirmation", async () => {
    const starter = vi.fn((options: SubmissionUploadOptions) => new Promise<SubmissionProcessingJob>((_, reject) => {
      options.signal?.addEventListener(
        "abort",
        () => reject(new DOMException("上传已取消", "AbortError")),
        { once: true },
      );
    }));
    render(<Harness starter={starter} />);

    fireEvent.click(screen.getByRole("button", { name: "上传" }));
    fireEvent.click(await screen.findByRole("button", { name: "取消上传" }));

    await waitFor(() => expect(screen.getByText("上传已取消，当前投稿未发生变化。")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "重新上传" })).toBeEnabled();
  });
});

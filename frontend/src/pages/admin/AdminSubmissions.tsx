import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Stack, Tab, Tabs, Typography } from "@mui/material";
import { useConfirm } from "material-ui-confirm";
import { useSnackbar } from "notistack";
import { Check, Download, Trash2 } from "lucide-react";
import { api, type StoredFileRead, type SubmissionProcessingJob, type Track } from "../../api/v1";
import { ChartPreviewDialog } from "../../components/ChartPreviewDialog";
import { DownloadPreparationDialog } from "../../components/DownloadPreparationDialog";
import { ResourceState, useApiResource } from "../../components/PagePrimitives";
import { queryKeys } from "../../api/queryKeys";
import { useSubmissionUploadDialog } from "../../components/SubmissionUploadDialog";
import { BatchDeleteDialog } from "./AdminShared";
import { SubmissionDataGrid } from "./SubmissionDataGrid";

export default function AdminSubmissions() {
  const confirm = useConfirm();
  const { enqueueSnackbar } = useSnackbar();
  const [filter, setFilter] = useState<Track | "all">("all");
  const files = useApiResource(queryKeys.submissions.admin(filter), () => api.adminSubmissions(filter));
  const jobs = useApiResource(queryKeys.submissions.adminJobs, api.adminSubmissionProcessingJobs, true, {
    refreshInterval: (current) => current?.some((job) => job.status === "queued" || job.status === "processing") ? 3000 : 0,
    refreshWhenHidden: false,
  });
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");
  const [previewFile, setPreviewFile] = useState<StoredFileRead | null>(null);
  const handleQueued = useCallback((job: SubmissionProcessingJob) => {
    jobs.setData((current) => [job, ...(current ?? []).filter((item) => item.id !== job.id)]);
  }, [jobs.setData]);
  const uploadDialog = useSubmissionUploadDialog(handleQueued);
  const hasActiveJobs = jobs.data?.some((job) => job.status === "queued" || job.status === "processing") ?? false;
  useEffect(() => {
    if (hasActiveJobs && !jobs.validating) void files.reload();
  }, [files.reload, hasActiveJobs, jobs.data, jobs.validating]);
  async function remove(file: StoredFileRead) { const result = await confirm({ title: "删除投稿", description: `确认删除 ${file.file_name}？此操作不可撤销。`, confirmationButtonProps: { color: "error" } }); if (!result.confirmed) return; try { await api.deleteAdminSubmission(file.id); setSelected((current) => { const next = new Set(current); next.delete(file.id); return next; }); files.updateData((items) => items.filter((item) => item.id !== file.id)); } catch (err) { setError(err instanceof Error ? err.message : "删除失败"); } }
  async function removeSelected() { setDeleting(true); setError(""); try { await api.batchDeleteAdminSubmissions([...selected]); files.updateData((items) => items.filter((item) => !selected.has(item.id))); setSelected(new Set()); setDeleteOpen(false); } catch (err) { setError(err instanceof Error ? err.message : "批量删除失败"); setDeleteOpen(false); } finally { setDeleting(false); } }
  async function downloadSelected() { if (!selected.size || downloading) return; setDownloading(true); setError(""); try { await api.downloadAdminSubmissions([...selected], filter); enqueueSnackbar("下载请求已开始，请查看浏览器下载列表", { variant: "success" }); } catch (err) { setError(err instanceof Error ? err.message : "下载失败"); } finally { setDownloading(false); } }
  async function rebuildPreview(file: StoredFileRead) { setError(""); try { const manifest = await api.rebuildSubmissionPreview(file.id); files.updateData((items) => items.map((item) => item.id === file.id ? { ...item, preview_status: manifest.status, preview_message: manifest.message } : item)); enqueueSnackbar("预览素材已进入重新生成队列", { variant: "info" }); } catch (err) { setError(err instanceof Error ? err.message : "重新生成预览失败"); } }
  async function rebuildResources(file: StoredFileRead) { setError(""); try { const job = await api.rebuildSubmissionResources(file.id); handleQueued(job); enqueueSnackbar("投稿资源已进入重新生成队列", { variant: "info" }); } catch (err) { setError(err instanceof Error ? err.message : "重新生成资源失败"); } }
  async function replace(file: StoredFileRead, next?: File) { if (!next) return; setError(""); await uploadDialog.start(next, (options) => api.replaceAdminSubmission(file.id, next, undefined, options)); }
  return <Stack spacing={2}>
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between" }}><Tabs value={filter} onChange={(_, value) => { setFilter(value); setSelected(new Set()); }}><Tab value="all" label="全部" disabled={downloading} /><Tab value="normal" label="普通" disabled={downloading} /><Tab value="j" label="J 赛道" disabled={downloading} /><Tab value="exhibition" label="场外" disabled={downloading} /></Tabs><Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}><Button variant="outlined" startIcon={<Check size={16} />} disabled={downloading} onClick={() => setSelected(new Set(files.data?.map((item) => item.id) || []))}>全选</Button><Button variant="contained" startIcon={<Download size={16} />} disabled={!selected.size || downloading} onClick={() => void downloadSelected()}>{downloading ? "正在准备…" : `下载 ${selected.size} 份`}</Button><Button color="error" variant="outlined" startIcon={<Trash2 size={16} />} disabled={!selected.size || downloading} onClick={() => setDeleteOpen(true)}>删除 {selected.size} 份</Button></Stack></Stack>
    {error ? <Alert severity="error">{error}</Alert> : null}<ResourceState loading={(files.loading && files.data === null) || (jobs.loading && jobs.data === null)} error={files.error || jobs.error} empty={!files.data?.length && !jobs.data?.length ? "暂无投稿" : undefined} />
    {jobs.data?.map((job) => <Alert key={job.id} severity={job.status === "failed" ? "error" : "info"}><Typography variant="body2" sx={{ fontWeight: 700 }}>{job.replace_submission_id ? "投稿替换" : "新投稿"} · {job.file_name}</Typography><Typography variant="caption">{job.message}</Typography></Alert>)}
    {files.data?.length ? <SubmissionDataGrid files={files.data} selected={selected} setSelected={setSelected} downloading={downloading} setPreviewFile={setPreviewFile} rebuildPreview={rebuildPreview} rebuildResources={rebuildResources} replace={replace} remove={remove} setError={setError} /> : null}
    <BatchDeleteDialog open={deleteOpen} count={selected.size} label="份投稿" busy={deleting} onClose={() => setDeleteOpen(false)} onConfirm={() => void removeSelected()} />
    <DownloadPreparationDialog open={downloading} count={selected.size} unit="份投稿" />
    <ChartPreviewDialog open={Boolean(previewFile)} source="submission" sourceId={previewFile?.id ?? null} title={previewFile?.file_name ?? "投稿"} onClose={() => setPreviewFile(null)} onDownload={() => previewFile ? api.downloadAdminSubmission(previewFile.id) : Promise.resolve()} />
    {uploadDialog.dialog}
  </Stack>;
}

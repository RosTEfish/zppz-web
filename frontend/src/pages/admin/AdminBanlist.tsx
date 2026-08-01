import { useMemo, useState } from "react";
import { Alert, Box, Button, Chip, Paper, Stack, Typography } from "@mui/material";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";
import { useSnackbar } from "notistack";
import { Check, FileUp, Eye, Upload } from "lucide-react";
import { api, type BanImportPreviewRead, type BanImportRead } from "../../api/v1";
import { ResourceState, useApiResource } from "../../components/PagePrimitives";
import { queryKeys } from "../../api/queryKeys";
import { dataGridZhCN } from "../../components/dataGridLocale";


function statusLabel(status: string): string {
  if (status === "published") return "当前发布";
  if (status === "superseded") return "历史版本";
  return "草稿";
}


export default function AdminBanlist() {
  const { enqueueSnackbar } = useSnackbar();
  const imports = useApiResource(queryKeys.admin.banImports, api.adminBanlistImports);
  const [preview, setPreview] = useState<BanImportPreviewRead | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const previewColumns = useMemo<GridColDef<BanImportPreviewRead["entries"][number]>[]>(() => [
    { field: "title", headerName: "曲目", minWidth: 180, flex: 1 },
    { field: "artist", headerName: "作者", minWidth: 150, flex: 0.8 },
    { field: "round", headerName: "赛事届次", minWidth: 120, flex: 0.5 },
    { field: "note", headerName: "备注", minWidth: 180, flex: 1, valueGetter: (value) => value || "-" },
  ], []);
  const importColumns = useMemo<GridColDef<BanImportRead>[]>(() => [
    { field: "file_name", headerName: "文件", minWidth: 220, flex: 1, renderCell: ({ row }) => <Stack sx={{ justifyContent: "center", height: "100%" }}><Typography variant="body2" sx={{ fontWeight: 700 }}>{row.file_name}</Typography><Typography variant="caption" color="text.secondary">SHA-256 {row.file_sha256.slice(0, 12)}…</Typography></Stack> },
    { field: "status", headerName: "状态", width: 130, renderCell: ({ row }) => <Chip size="small" color={row.status === "published" ? "success" : "default"} icon={row.status === "published" ? <Check size={14} /> : undefined} label={statusLabel(row.status)} /> },
    { field: "entry_count", headerName: "曲目数", width: 100 },
    { field: "created_at", headerName: "上传时间", minWidth: 180, flex: 0.6, valueFormatter: (value) => new Date(String(value)).toLocaleString("zh-CN", { hour12: false }) },
    { field: "actions", headerName: "操作", width: 130, sortable: false, filterable: false, renderCell: ({ row }) => <Button size="small" aria-label={`查看 ${row.file_name} 预览`} startIcon={<Eye size={15} />} onClick={() => void showPreview(row.id)}>查看预览</Button> },
  ], []);

  async function upload(file?: File) {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      setPreview(await api.importBanlist(file));
      await imports.reload();
      enqueueSnackbar("Ban 曲文件已解析，请检查预览后发布", { variant: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ban 曲导入失败");
    } finally {
      setBusy(false);
    }
  }

  async function showPreview(id: number) {
    try {
      setPreview(await api.previewBanlist(id));
      setError("");
    } catch (err) { setError(err instanceof Error ? err.message : "预览加载失败"); }
  }

  async function publish() {
    if (!preview) return;
    setBusy(true);
    try {
      await api.publishBanlist(preview.id);
      enqueueSnackbar("Ban 曲版本已发布，查重已切换到新版本", { variant: "success" });
      setPreview(null);
      await imports.reload();
    } catch (err) { setError(err instanceof Error ? err.message : "发布失败"); }
    finally { setBusy(false); }
  }

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}>
        <Box><Typography variant="h3">往届 Ban 曲库</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>上传 Excel 后先预览解析结果，再发布为查重使用的版本。</Typography></Box>
        <Button component="label" variant="contained" disabled={busy} startIcon={<FileUp size={17} />}>上传 .xlsx<input hidden type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={(event) => { void upload(event.target.files?.[0]); event.currentTarget.value = ""; }} /></Button>
      </Stack>
      {error ? <Alert severity="error">{error}</Alert> : null}
      {preview ? <Paper variant="outlined" sx={{ p: 2 }}><Stack spacing={1.5}><Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}><Box><Typography variant="h3">导入预览：{preview.file_name}</Typography><Typography variant="body2" color="text.secondary">解析到 {preview.entry_count} 首，发现 {preview.issue_count} 个提示。</Typography></Box><Button variant="contained" disabled={busy || !preview.entry_count} startIcon={<Upload size={16} />} onClick={() => void publish()}>发布此版本</Button></Stack>{preview.issues.length ? <Alert severity="warning"><Stack spacing={0.25}>{preview.issues.slice(0, 8).map((issue) => <Typography variant="body2" key={issue}>{issue}</Typography>)}{preview.issues.length > 8 ? <Typography variant="caption">其余 {preview.issues.length - 8} 个提示未展开。</Typography> : null}</Stack></Alert> : <Alert severity="success">未发现解析问题，可以发布。</Alert>}<Paper variant="outlined" sx={{ height: 430 }}><DataGrid rows={preview.entries.slice(0, 200)} columns={previewColumns} getRowId={(row) => row.id} disableRowSelectionOnClick initialState={{ pagination: { paginationModel: { page: 0, pageSize: 50 } } }} pageSizeOptions={[50]} localeText={dataGridZhCN} sx={{ border: 0 }} /></Paper></Stack></Paper> : null}
      <ResourceState loading={imports.loading} error={imports.error} empty="还没有导入 Ban 曲版本" />
      {imports.data?.length ? <Paper variant="outlined" sx={{ height: Math.min(620, 112 + imports.data.length * 58), minHeight: 260 }}><DataGrid rows={imports.data} columns={importColumns} getRowId={(row) => row.id} getRowHeight={() => 58} disableRowSelectionOnClick initialState={{ pagination: { paginationModel: { page: 0, pageSize: 25 } } }} pageSizeOptions={[25, 50, 100]} localeText={dataGridZhCN} sx={{ border: 0 }} /></Paper> : null}
    </Stack>
  );
}

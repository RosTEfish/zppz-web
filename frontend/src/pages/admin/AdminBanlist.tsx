import { useState } from "react";
import { Alert, Box, Button, Chip, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from "@mui/material";
import { useSnackbar } from "notistack";
import { Check, FileUp, Eye, Upload } from "lucide-react";
import { api, type BanImportPreviewRead } from "../../api/v1";
import { ResourceState, useApiResource } from "../../components/PagePrimitives";
import { queryKeys } from "../../api/queryKeys";


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
      {preview ? <Paper variant="outlined" sx={{ p: 2 }}><Stack spacing={1.5}><Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}><Box><Typography variant="h3">导入预览：{preview.file_name}</Typography><Typography variant="body2" color="text.secondary">解析到 {preview.entry_count} 首，发现 {preview.issue_count} 个提示。</Typography></Box><Button variant="contained" disabled={busy || !preview.entry_count} startIcon={<Upload size={16} />} onClick={() => void publish()}>发布此版本</Button></Stack>{preview.issues.length ? <Alert severity="warning"><Stack spacing={0.25}>{preview.issues.slice(0, 8).map((issue) => <Typography variant="body2" key={issue}>{issue}</Typography>)}{preview.issues.length > 8 ? <Typography variant="caption">其余 {preview.issues.length - 8} 个提示未展开。</Typography> : null}</Stack></Alert> : <Alert severity="success">未发现解析问题，可以发布。</Alert>}<TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 420 }}><Table stickyHeader size="small"><TableHead><TableRow><TableCell>曲目</TableCell><TableCell>作者</TableCell><TableCell>赛事届次</TableCell><TableCell>备注</TableCell></TableRow></TableHead><TableBody>{preview.entries.slice(0, 200).map((entry) => <TableRow key={entry.id}><TableCell>{entry.title}</TableCell><TableCell>{entry.artist}</TableCell><TableCell>{entry.round}</TableCell><TableCell>{entry.note || "-"}</TableCell></TableRow>)}</TableBody></Table></TableContainer></Stack></Paper> : null}
      <ResourceState loading={imports.loading} error={imports.error} empty="还没有导入 Ban 曲版本" />
      {imports.data?.length ? <TableContainer component={Paper} variant="outlined"><Table size="small"><TableHead><TableRow><TableCell>文件</TableCell><TableCell>状态</TableCell><TableCell>曲目数</TableCell><TableCell>上传时间</TableCell><TableCell align="right">操作</TableCell></TableRow></TableHead><TableBody>{imports.data.map((item) => <TableRow key={item.id}><TableCell><Typography variant="body2" sx={{ fontWeight: 700 }}>{item.file_name}</Typography><Typography variant="caption" color="text.secondary">SHA-256 {item.file_sha256.slice(0, 12)}…</Typography></TableCell><TableCell><Chip size="small" color={item.status === "published" ? "success" : "default"} icon={item.status === "published" ? <Check size={14} /> : undefined} label={statusLabel(item.status)} /></TableCell><TableCell>{item.entry_count}</TableCell><TableCell>{new Date(item.created_at).toLocaleString("zh-CN", { hour12: false })}</TableCell><TableCell align="right"><Button size="small" startIcon={<Eye size={15} />} onClick={() => void showPreview(item.id)}>查看预览</Button></TableCell></TableRow>)}</TableBody></Table></TableContainer> : null}
    </Stack>
  );
}

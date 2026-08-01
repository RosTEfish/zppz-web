import { useEffect, useMemo, useState } from "react";
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, FormControl, FormControlLabel, FormHelperText, IconButton, InputLabel, MenuItem, Paper, Select, Stack, Switch, TextField, Tooltip, Typography } from "@mui/material";
import { DataGrid, type GridColDef, type GridRowSelectionModel } from "@mui/x-data-grid";
import { Check, FileArchive, Pencil, RefreshCw, Save as SaveIcon, Trash2 } from "lucide-react";
import { api, type AuthorCandidateAdmin, type GuessChartRead } from "../../api/v1";
import { type ApiResource, ResourceState, useApiResource } from "../../components/PagePrimitives";
import { queryKeys } from "../../api/queryKeys";
import { BatchDeleteDialog } from "./AdminShared";
import { useConfirm } from "material-ui-confirm";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { chartSchema, type ChartFormValues } from "../../forms/schemas";
import { dataGridZhCN } from "../../components/dataGridLocale";
import { identityLabel } from "../../identity";

export default function AdminGuess() {
  const charts = useApiResource(queryKeys.guess.adminCharts, api.adminCharts);
  const issues = useApiResource(queryKeys.guess.issues, api.importIssues);
  const candidates = useApiResource(queryKeys.guess.candidates, api.authorCandidates);
  const confirm = useConfirm();
  const [editing, setEditing] = useState<GuessChartRead | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [summary, setSummary] = useState("");
  const [error, setError] = useState("");
  async function importArchive(file?: File) { if (!file) return; try { const result = await api.importCharts(file); setSummary(`已新增 ${result.charts.length} 张谱面`); setSelected(new Set()); await Promise.all([charts.reload(), issues.reload()]); } catch (err) { setError(err instanceof Error ? err.message : "导入失败"); } }
  async function parseAll() { try { const result = await api.parseSubmissions(); setSummary(`扫描 ${result.scanned}，新增 ${result.created}，更新 ${result.updated}，删除 ${result.deleted}，问题 ${result.issues}`); setSelected(new Set()); await Promise.all([charts.reload(), issues.reload()]); } catch (err) { setError(err instanceof Error ? err.message : "解析失败"); } }
  async function remove(chart: GuessChartRead) { const result = await confirm({ title: "删除谱面", description: `确认删除《${chart.title}》${chart.level}？此操作不可撤销。`, confirmationButtonProps: { color: "error" } }); if (!result.confirmed) return; try { await api.deleteChart(chart.id); setSelected((current) => { const next = new Set(current); next.delete(chart.id); return next; }); charts.updateData((items) => items.filter((item) => item.id !== chart.id)); } catch (err) { setError(err instanceof Error ? err.message : "删除失败"); } }
  async function removeSelected() { setDeleting(true); setError(""); try { const result = await api.batchDeleteAdminCharts([...selected]); setSummary(result.message); charts.updateData((items) => items.filter((item) => !selected.has(item.id))); setSelected(new Set()); setDeleteOpen(false); await issues.reload(); } catch (err) { setError(err instanceof Error ? err.message : "批量删除失败"); setDeleteOpen(false); } finally { setDeleting(false); } }
  const columns = useMemo<GridColDef<GuessChartRead>[]>(() => [
    { field: "title", headerName: "谱面", minWidth: 180, flex: 1 },
    { field: "author", headerName: "曲师", minWidth: 130, flex: 0.7 },
    { field: "designer", headerName: "谱师", minWidth: 130, flex: 0.7, valueGetter: (value) => value || "-" },
    { field: "level", headerName: "等级", width: 90 },
    { field: "lane", headerName: "赛道", width: 90, valueFormatter: (value) => value === "j" ? "J" : value === "exhibition" ? "场外" : "普通" },
    { field: "source_submission_type", headerName: "来源", width: 110 },
    { field: "actions", headerName: "操作", width: 110, sortable: false, filterable: false, renderCell: ({ row }) => <><Tooltip title="编辑"><IconButton size="small" aria-label={`编辑谱面 ${row.title} ${row.level}`} onClick={() => setEditing(row)}><Pencil size={16} /></IconButton></Tooltip><Tooltip title="删除"><IconButton size="small" color="error" aria-label={`删除谱面 ${row.title} ${row.level}`} onClick={() => void remove(row)}><Trash2 size={16} /></IconButton></Tooltip></> },
  ], []);
  const selectionModel: GridRowSelectionModel = { type: "include", ids: new Set(selected) };
  return <Stack spacing={3}>
    <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}><Button component="label" variant="contained" startIcon={<FileArchive size={17} />}>新增谱面<input hidden type="file" accept=".zip,.7z,.rar" onChange={(event) => { void importArchive(event.target.files?.[0]); event.currentTarget.value = ""; }} /></Button><Button variant="outlined" startIcon={<RefreshCw size={17} />} onClick={() => void parseAll()}>重新解析全部来源</Button><Button variant="outlined" startIcon={<Check size={17} />} disabled={!charts.data?.length} onClick={() => setSelected(new Set(charts.data?.map((chart) => chart.id) || []))}>全选</Button><Button color="error" variant="outlined" startIcon={<Trash2 size={17} />} disabled={!selected.size} onClick={() => setDeleteOpen(true)}>删除 {selected.size} 项</Button></Stack>
    {summary ? <Alert severity="success">{summary}</Alert> : null}{error ? <Alert severity="error">{error}</Alert> : null}<ResourceState loading={charts.loading} error={charts.error} empty={!charts.data?.length ? "暂无谱面" : undefined} />
    {charts.data?.length ? <Paper variant="outlined" sx={{ height: Math.min(700, 112 + charts.data.length * 52), minHeight: 320 }}><DataGrid rows={charts.data} columns={columns} getRowId={(row) => row.id} checkboxSelection disableRowSelectionOnClick rowSelectionModel={selectionModel} onRowSelectionModelChange={(model) => setSelected(new Set([...model.ids].map(Number)))} initialState={{ pagination: { paginationModel: { page: 0, pageSize: 25 } } }} pageSizeOptions={[25, 50, 100]} localeText={dataGridZhCN} sx={{ border: 0 }} /></Paper> : null}
    <AuthorCandidatesEditor resource={candidates} setError={setError} />
    {issues.data?.length ? <Paper variant="outlined" sx={{ p: 2 }}><Typography variant="h3" sx={{ mb: 1.5 }}>解析问题</Typography><Stack spacing={1}>{issues.data.map((issue) => <Alert key={issue.id} severity="warning"><strong>{issue.file_name || issue.source_type}</strong>：{issue.message}</Alert>)}</Stack></Paper> : null}
    <ChartEditDialog chart={editing} onClose={() => setEditing(null)} onSaved={(updated) => { charts.updateData((items) => items.map((item) => item.id === updated.id ? updated : item)); setEditing(null); }} />
    <BatchDeleteDialog open={deleteOpen} count={selected.size} label="张谱面" busy={deleting} onClose={() => setDeleteOpen(false)} onConfirm={() => void removeSelected()} />
  </Stack>;
}

function AuthorCandidatesEditor({ resource, setError }: { resource: ApiResource<AuthorCandidateAdmin[]>; setError: (value: string) => void }) {
  const [rows, setRows] = useState<AuthorCandidateAdmin[]>([]);
  useEffect(() => { if (resource.data) setRows(resource.data); }, [resource.data]);
  async function save() { try { await api.saveAuthorCandidates(rows.map((row) => ({ user_id: row.user.id, display_id: row.display_id }))); await resource.reload(); } catch (err) { setError(err instanceof Error ? err.message : "保存失败"); } }
  return <Paper variant="outlined" sx={{ p: 2 }}><Stack direction="row" sx={{ mb: 1.5, justifyContent: "space-between", alignItems: "center" }}><Typography variant="h3">谱师候选展示 ID</Typography><Button variant="outlined" size="small" startIcon={<SaveIcon size={15} />} onClick={() => void save()}>保存展示 ID</Button></Stack><Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, 1fr)" }, gap: 1 }}>{rows.map((row, index) => <Paper key={row.user.id} variant="outlined" sx={{ p: 1.25 }}><Stack direction="row" spacing={1} sx={{ alignItems: "center" }}><Box sx={{ flex: 1, minWidth: 0 }}><Typography variant="body2" sx={{ fontWeight: 650 }}>{row.user.user_code}</Typography><Typography variant="caption" color="text.secondary">{identityLabel(row.user.identity)} · {row.song_count} 首曲目</Typography></Box><TextField size="small" label="展示 ID" value={row.display_id} onChange={(event) => setRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, display_id: event.target.value } : item))} sx={{ width: 150 }} /></Stack></Paper>)}</Box></Paper>;
}

function ChartEditDialog({ chart, onClose, onSaved }: { chart: GuessChartRead | null; onClose: () => void; onSaved: (chart: GuessChartRead) => void }) {
  const [error, setError] = useState("");
  const { register, control, handleSubmit, reset, formState: { errors, isSubmitting } } = useForm<ChartFormValues>({ resolver: zodResolver(chartSchema), defaultValues: { title: "", author: "", designer: "", level: "", lane: "normal", guess_group_key: "", is_self_selected: false } });
  useEffect(() => { if (chart) reset({ title: chart.title, author: chart.author, designer: chart.designer, level: chart.level, lane: chart.lane as ChartFormValues["lane"], guess_group_key: chart.guess_group_key, is_self_selected: chart.is_self_selected }); }, [chart, reset]);
  if (!chart) return null;
  const save = handleSubmit(async (form) => { setError(""); try { onSaved(await api.updateChart(chart.id, form)); } catch (err) { setError(err instanceof Error ? err.message : "保存失败"); } });
  return <Dialog open onClose={isSubmitting ? undefined : onClose} fullWidth maxWidth="sm"><DialogTitle>编辑谱面</DialogTitle><DialogContent><Stack spacing={2} sx={{ pt: 1 }}><TextField label="标题" {...register("title")} error={Boolean(errors.title)} helperText={errors.title?.message} /><TextField label="曲师" {...register("author")} error={Boolean(errors.author)} helperText={errors.author?.message} /><TextField label="谱师" {...register("designer")} error={Boolean(errors.designer)} helperText={errors.designer?.message} /><TextField label="等级" {...register("level")} error={Boolean(errors.level)} helperText={errors.level?.message} /><Controller name="lane" control={control} render={({ field, fieldState }) => <FormControl error={Boolean(fieldState.error)}><InputLabel>赛道</InputLabel><Select {...field} label="赛道"><MenuItem value="normal">普通</MenuItem><MenuItem value="j">J</MenuItem><MenuItem value="exhibition">场外</MenuItem></Select>{fieldState.error ? <FormHelperText>{fieldState.error.message}</FormHelperText> : null}</FormControl>} /><TextField label="猜测分组" {...register("guess_group_key")} error={Boolean(errors.guess_group_key)} helperText={errors.guess_group_key?.message} /><Controller name="is_self_selected" control={control} render={({ field }) => <FormControlLabel control={<Switch checked={field.value} onChange={field.onChange} />} label="自选谱面" />} />{error ? <Alert severity="error">{error}</Alert> : null}</Stack></DialogContent><DialogActions><Button disabled={isSubmitting} onClick={onClose}>取消</Button><Button variant="contained" disabled={isSubmitting} startIcon={<SaveIcon size={16} />} onClick={() => void save()}>保存</Button></DialogActions></Dialog>;
}

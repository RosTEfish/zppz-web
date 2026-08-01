import { useMemo, type Dispatch, type SetStateAction } from "react";
import { Chip, IconButton, Paper, Stack, Tooltip, Typography } from "@mui/material";
import { DataGrid, type GridColDef, type GridRowSelectionModel } from "@mui/x-data-grid";
import { Download, Eye, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import { api, formatDuration, formatMB, formatTime, type StoredFileRead } from "../../api/v1";
import { dataGridZhCN } from "../../components/dataGridLocale";

interface SubmissionDataGridProps {
  files: StoredFileRead[];
  selected: Set<number>;
  setSelected: Dispatch<SetStateAction<Set<number>>>;
  downloading: boolean;
  setPreviewFile: (file: StoredFileRead) => void;
  rebuildPreview: (file: StoredFileRead) => Promise<void>;
  rebuildResources: (file: StoredFileRead) => Promise<void>;
  replace: (file: StoredFileRead, next?: File) => Promise<void>;
  remove: (file: StoredFileRead) => Promise<void>;
  setError: (message: string) => void;
}

export function SubmissionDataGrid({ files, selected, setSelected, downloading, setPreviewFile, rebuildPreview, rebuildResources, replace, remove, setError }: SubmissionDataGridProps) {
  const columns = useMemo<GridColDef<StoredFileRead>[]>(() => [
    { field: "file_name", headerName: "曲目 / 文件", minWidth: 300, flex: 1.4, sortable: false, renderCell: ({ row }) => <Stack sx={{ justifyContent: "center", height: "100%", minWidth: 0 }}><Typography sx={{ fontWeight: 650 }}>{row.source_song?.song_name || "未关联曲目"}</Typography><Typography variant="caption" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>{row.file_name} · {formatMB(row.file_size)}</Typography>{row.preview_status ? <Typography variant="caption" color={row.preview_status === "ready" ? "success.main" : row.preview_status === "failed" || row.preview_status === "unsupported" ? "warning.main" : "text.secondary"}>预览：{row.preview_status === "ready" ? "就绪" : row.preview_message || "准备中"}</Typography> : null}<Typography variant="caption" color={row.public_package_status === "failed" ? "error.main" : "text.secondary"}>公开包：{row.public_package_status === "ready" ? "就绪" : row.public_package_status === "failed" ? row.public_package_message || "生成失败" : "准备中"} · 视频：{row.video_status === "ready" ? "就绪" : row.video_status === "failed" ? "失败，使用静态背景" : row.video_status === "processing" ? "准备中" : "无"}</Typography></Stack> },
    { field: "user", headerName: "投稿人", minWidth: 130, flex: 0.6, sortable: false, valueGetter: (_value, row) => row.user?.display_name || row.user?.user_code || "-" },
    { field: "source_kind", headerName: "来源", width: 90, valueGetter: (_value, row) => row.track === "exhibition" ? "场外" : row.source_kind === "self" ? "自选" : "抽中" },
    { field: "track", headerName: "赛道", width: 90, renderCell: ({ row }) => <Chip size="small" color={row.track === "j" ? "secondary" : row.track === "exhibition" ? "info" : "default"} label={row.track === "j" ? "J" : row.track === "exhibition" ? "场外" : "普通"} /> },
    { field: "track_duration_seconds", headerName: "时长", width: 90, valueFormatter: (value) => formatDuration(value as number | null | undefined) },
    { field: "created_at", headerName: "时间", minWidth: 150, flex: 0.5, valueFormatter: (value) => formatTime(String(value)) },
    { field: "actions", headerName: "操作", width: 250, sortable: false, filterable: false, renderCell: ({ row }) => <>
      <Tooltip title={row.preview_status === "ready" ? "在线预览" : "预览尚未就绪"}><span><IconButton size="small" disabled={row.preview_status !== "ready"} aria-label={`预览投稿 ${row.file_name}`} onClick={() => setPreviewFile(row)}><Eye size={16} /></IconButton></span></Tooltip>
      {row.preview_status === "failed" || row.preview_status === "unsupported" || !row.preview_status ? <Tooltip title="重新生成预览"><IconButton size="small" aria-label={`重新生成预览 ${row.file_name}`} onClick={() => void rebuildPreview(row)}><RotateCcw size={16} /></IconButton></Tooltip> : null}
      {row.public_package_status === "failed" || row.video_status === "failed" ? <Tooltip title="重新生成全部投稿资源"><IconButton size="small" aria-label={`重新生成投稿资源 ${row.file_name}`} onClick={() => void rebuildResources(row)}><RotateCcw size={16} /></IconButton></Tooltip> : null}
      <Tooltip title={row.public_package_status === "ready" ? "下载" : "公开包尚未就绪"}><span><IconButton size="small" disabled={row.public_package_status !== "ready"} aria-label={`下载投稿 ${row.file_name}`} onClick={() => void api.downloadAdminSubmission(row.id).catch((err) => setError(err.message))}><Download size={16} /></IconButton></span></Tooltip>
      <Tooltip title="替换"><IconButton component="label" size="small" aria-label={`替换投稿 ${row.file_name}`}><RefreshCw size={16} /><input hidden type="file" accept=".zip,.7z,.rar" onChange={(event) => { const next = event.target.files?.[0]; void replace(row, next); event.currentTarget.value = ""; }} /></IconButton></Tooltip>
      <Tooltip title="删除"><IconButton size="small" color="error" aria-label={`删除投稿 ${row.file_name}`} onClick={() => void remove(row)}><Trash2 size={16} /></IconButton></Tooltip>
    </> },
  ], [rebuildPreview, rebuildResources, remove, replace, setError, setPreviewFile]);
  const selectionModel: GridRowSelectionModel = { type: "include", ids: new Set(selected) };
  return <Paper variant="outlined" sx={{ height: Math.min(760, 112 + files.length * 96), minHeight: 340 }}><DataGrid
    rows={files}
    columns={columns}
    getRowId={(row) => row.id}
    getRowHeight={() => 96}
    checkboxSelection
    disableRowSelectionOnClick
    isRowSelectable={() => !downloading}
    rowSelectionModel={selectionModel}
    onRowSelectionModelChange={(model) => setSelected(new Set([...model.ids].map(Number)))}
    initialState={{ pagination: { paginationModel: { page: 0, pageSize: 25 } } }}
    pageSizeOptions={[25, 50, 100]}
    localeText={{ ...dataGridZhCN, checkboxSelectionHeaderName: "投稿选择", checkboxSelectionSelectAllRows: "选择全部投稿", checkboxSelectionUnselectAllRows: "取消选择全部投稿", checkboxSelectionSelectRow: "选择投稿", checkboxSelectionUnselectRow: "取消选择投稿" }}
    sx={{ border: 0 }}
  /></Paper>;
}

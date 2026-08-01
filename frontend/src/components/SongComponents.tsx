import { useEffect, useState } from "react";
import { Alert, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControl, FormHelperText, IconButton, InputLabel, MenuItem, Paper, Select, Stack, TextField, Tooltip, Typography } from "@mui/material";
import { Pencil, Save, Trash2 } from "lucide-react";
import { DataGrid, type GridColDef, type GridRowSelectionModel } from "@mui/x-data-grid";
import { dataGridZhCN } from "./dataGridLocale";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { SongPayload, SongRead } from "../api/v1";
import { BanCheckPanel, canSubmitWithBanCheck, useBanCheck } from "./BanCheckPanel";
import { songSchema, type SongFormValues } from "../forms/schemas";


const EMPTY_SONG: SongPayload = { song_name: "", artist: "", remark: "" };
const EMPTY_SONG_FORM: SongFormValues = { song_name: "", artist: "", remark: "" };


export function SongTable({ songs, onEdit, onDelete, showSubmitter = false, selectedIds, onToggleSelection, onToggleAll }: { songs: SongRead[]; onEdit?: (song: SongRead) => void; onDelete?: (song: SongRead) => void; showSubmitter?: boolean; selectedIds?: ReadonlySet<number>; onToggleSelection?: (songId: number) => void; onToggleAll?: (checked: boolean) => void }) {
  const selectionEnabled = Boolean(onToggleSelection && onToggleAll);
  const columns: GridColDef<SongRead>[] = [
    { field: "song_name", headerName: "曲目", minWidth: 180, flex: 1, renderCell: ({ row }) => <Stack sx={{ justifyContent: "center", height: "100%" }}><Typography variant="body2" sx={{ fontWeight: 650 }}>{row.song_name}</Typography><Typography variant="caption" color="text.secondary">#{row.id}</Typography></Stack> },
    { field: "artist", headerName: "曲师", minWidth: 140, flex: 0.7 },
    { field: "song_type", headerName: "分类", width: 90, renderCell: ({ value }) => <Chip size="small" label={value} /> },
    ...(showSubmitter ? [{ field: "submitter", headerName: "投稿人", minWidth: 130, flex: 0.6, valueGetter: (_value, row) => row.submitter?.display_name || row.submitter?.user_code || "-" } satisfies GridColDef<SongRead>] : []),
    { field: "remark", headerName: "备注", minWidth: 180, flex: 1, valueGetter: (value) => value || "-" },
    ...((onEdit || onDelete) ? [{ field: "actions", headerName: "操作", width: 112, sortable: false, filterable: false, renderCell: ({ row }) => <>{onEdit ? <Tooltip title="编辑"><IconButton size="small" aria-label={`编辑 ${row.song_name}`} onClick={() => onEdit(row)}><Pencil size={16} /></IconButton></Tooltip> : null}{onDelete ? <Tooltip title="删除"><IconButton size="small" aria-label={`删除 ${row.song_name}`} color="error" onClick={() => onDelete(row)}><Trash2 size={16} /></IconButton></Tooltip> : null}</> } satisfies GridColDef<SongRead>] : []),
  ];
  const rowSelectionModel: GridRowSelectionModel = { type: "include", ids: new Set(selectedIds ?? []) };
  function updateSelection(model: GridRowSelectionModel) {
    const next = model.type === "include" ? new Set(model.ids) : new Set(songs.map((song) => song.id).filter((id) => !model.ids.has(id)));
    if (next.size === 0 || next.size === songs.length) { onToggleAll?.(next.size === songs.length); return; }
    for (const song of songs) if (next.has(song.id) !== Boolean(selectedIds?.has(song.id))) onToggleSelection?.(song.id);
  }
  return <Paper variant="outlined" sx={{ height: Math.min(650, 112 + songs.length * 52), minHeight: 260 }}><DataGrid rows={songs} columns={columns} getRowId={(row) => row.id} checkboxSelection={selectionEnabled} disableRowSelectionOnClick rowSelectionModel={selectionEnabled ? rowSelectionModel : undefined} onRowSelectionModelChange={selectionEnabled ? updateSelection : undefined} initialState={{ pagination: { paginationModel: { pageSize: 25, page: 0 } } }} pageSizeOptions={[25, 50, 100]} localeText={dataGridZhCN} sx={{ border: 0 }} /></Paper>;
}


export function SongDialog({ song, onClose, onSave }: { song: SongRead | null; onClose: () => void; onSave: (payload: SongPayload) => Promise<void> }) {
  const [error, setError] = useState("");
  const { register, control, handleSubmit, reset, watch, formState: { errors, isSubmitting } } = useForm<SongFormValues>({ resolver: zodResolver(songSchema), defaultValues: EMPTY_SONG_FORM });
  const songName = watch("song_name");
  const artist = watch("artist");
  const banCheck = useBanCheck(songName, artist);
  useEffect(() => {
    if (song) {
      reset({ song_name: song.song_name, artist: song.artist, song_type: song.song_type as SongFormValues["song_type"], remark: song.remark });
      setError("");
    }
  }, [reset, song]);
  const save = handleSubmit(async (form) => {
    setError("");
    try { await onSave({ ...form, acknowledge_ban_warning: banCheck.acknowledged }); }
    catch (err) { setError(err instanceof Error ? err.message : "保存失败"); }
  });
  return <Dialog open={Boolean(song)} onClose={isSubmitting ? undefined : onClose} fullWidth maxWidth="sm"><DialogTitle>编辑曲目</DialogTitle><DialogContent><Stack spacing={2} sx={{ pt: 1 }}><TextField label="曲名" {...register("song_name")} error={Boolean(errors.song_name)} helperText={errors.song_name?.message} /><TextField label="曲师" {...register("artist")} error={Boolean(errors.artist)} helperText={errors.artist?.message} /><BanCheckPanel state={banCheck} compact /><Controller name="song_type" control={control} render={({ field, fieldState }) => <FormControl error={Boolean(fieldState.error)}><InputLabel>分类</InputLabel><Select {...field} value={field.value ?? ""} label="分类"><MenuItem value="A">A</MenuItem><MenuItem value="B">B</MenuItem><MenuItem value="C">C</MenuItem></Select>{fieldState.error ? <FormHelperText>{fieldState.error.message}</FormHelperText> : null}</FormControl>} /><TextField label="备注" multiline minRows={2} {...register("remark")} error={Boolean(errors.remark)} helperText={errors.remark?.message} />{error ? <Alert severity="error">{error}</Alert> : null}</Stack></DialogContent><DialogActions><Button disabled={isSubmitting} onClick={onClose}>取消</Button><Button variant="contained" disabled={isSubmitting || !canSubmitWithBanCheck(banCheck)} startIcon={<Save size={16} />} onClick={() => void save()}>保存</Button></DialogActions></Dialog>;
}


export { EMPTY_SONG };

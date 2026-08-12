import { useEffect, useState } from "react";
import { Alert, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControl, FormHelperText, IconButton, InputLabel, MenuItem, Paper, Select, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TablePagination, TableRow, TextField, Tooltip, Typography } from "@mui/material";
import { Pencil, Save, Trash2 } from "lucide-react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { SongPayload, SongRead } from "../api/v1";
import { BanCheckPanel, canSubmitWithBanCheck, useBanCheck } from "./BanCheckPanel";
import { songSchema, type SongFormValues } from "../forms/schemas";


const EMPTY_SONG: SongPayload = { song_name: "", artist: "", remark: "" };
const EMPTY_SONG_FORM: SongFormValues = { song_name: "", artist: "", remark: "" };


export function SongTable({ songs, onEdit, onDelete, showSubmitter = false, selectedIds, onToggleSelection, onToggleAll }: { songs: SongRead[]; onEdit?: (song: SongRead) => void; onDelete?: (song: SongRead) => void; showSubmitter?: boolean; selectedIds?: ReadonlySet<number>; onToggleSelection?: (songId: number) => void; onToggleAll?: (checked: boolean) => void }) {
  const selectionEnabled = Boolean(onToggleSelection && onToggleAll);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const pageCount = Math.max(1, Math.ceil(songs.length / pageSize));
  const safePage = Math.min(page, pageCount - 1);
  const rows = songs.slice(safePage * pageSize, safePage * pageSize + pageSize);
  const allSelected = songs.length > 0 && selectedIds?.size === songs.length;
  const someSelected = Boolean(selectedIds?.size) && !allSelected;

  return (
    <Paper variant="outlined">
      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow>
              {selectionEnabled ? (
                <TableCell padding="checkbox">
                  <Checkbox
                    indeterminate={someSelected}
                    checked={allSelected}
                    onChange={() => onToggleAll?.(!allSelected)}
                    slotProps={{ input: { "aria-label": "全选曲目" } }}
                  />
                </TableCell>
              ) : null}
              <TableCell>曲目</TableCell>
              <TableCell>曲师</TableCell>
              <TableCell>分类</TableCell>
              {showSubmitter ? <TableCell>投稿人</TableCell> : null}
              <TableCell>备注</TableCell>
              {(onEdit || onDelete) ? <TableCell align="right">操作</TableCell> : null}
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((song) => (
              <TableRow key={song.id} hover>
                {selectionEnabled ? (
                  <TableCell padding="checkbox">
                    <Checkbox
                      checked={Boolean(selectedIds?.has(song.id))}
                      onChange={() => onToggleSelection?.(song.id)}
                      slotProps={{ input: { "aria-label": `选择 ${song.song_name}` } }}
                    />
                  </TableCell>
                ) : null}
                <TableCell>
                  <Typography variant="body2" sx={{ fontWeight: 650 }}>{song.song_name}</Typography>
                  <Typography variant="caption" color="text.secondary">#{song.id}</Typography>
                </TableCell>
                <TableCell>{song.artist}</TableCell>
                <TableCell><Chip size="small" label={song.song_type} /></TableCell>
                {showSubmitter ? <TableCell>{song.submitter?.display_name || song.submitter?.user_code || "-"}</TableCell> : null}
                <TableCell>{song.remark || "-"}</TableCell>
                {(onEdit || onDelete) ? (
                  <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                    {onEdit ? <Tooltip title="编辑"><IconButton size="small" aria-label={`编辑 ${song.song_name}`} onClick={() => onEdit(song)}><Pencil size={16} /></IconButton></Tooltip> : null}
                    {onDelete ? <Tooltip title="删除"><IconButton size="small" aria-label={`删除 ${song.song_name}`} color="error" onClick={() => onDelete(song)}><Trash2 size={16} /></IconButton></Tooltip> : null}
                  </TableCell>
                ) : null}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      {songs.length > pageSize ? (
        <TablePagination
          component="div"
          count={songs.length}
          page={safePage}
          onPageChange={(_, nextPage) => setPage(nextPage)}
          rowsPerPage={pageSize}
          onRowsPerPageChange={(event) => { setPageSize(parseInt(event.target.value, 10)); setPage(0); }}
          rowsPerPageOptions={[25, 50, 100]}
          labelRowsPerPage="每页行数"
          labelDisplayedRows={({ from, to, count }) => `${from}–${to} / 共 ${count}`}
        />
      ) : null}
    </Paper>
  );
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

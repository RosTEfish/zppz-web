import { useEffect, useState } from "react";
import { Alert, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControl, IconButton, InputLabel, MenuItem, Paper, Select, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Tooltip, Typography } from "@mui/material";
import { Pencil, Save, Trash2 } from "lucide-react";
import type { SongPayload, SongRead } from "../api/v1";


const EMPTY_SONG: SongPayload = { song_name: "", artist: "", song_type: "A", remark: "" };


export function SongTable({ songs, onEdit, onDelete, showSubmitter = false, selectedIds, onToggleSelection, onToggleAll }: { songs: SongRead[]; onEdit: (song: SongRead) => void; onDelete: (song: SongRead) => void; showSubmitter?: boolean; selectedIds?: ReadonlySet<number>; onToggleSelection?: (songId: number) => void; onToggleAll?: (checked: boolean) => void }) {
  const selectionEnabled = Boolean(onToggleSelection && onToggleAll);
  const selectedCount = songs.reduce((count, song) => count + (selectedIds?.has(song.id) ? 1 : 0), 0);
  return (
    <TableContainer component={Paper} variant="outlined">
      <Table size="small"><TableHead><TableRow>{selectionEnabled ? <TableCell padding="checkbox"><Checkbox checked={selectedCount === songs.length} indeterminate={selectedCount > 0 && selectedCount < songs.length} onChange={(event) => onToggleAll?.(event.target.checked)} slotProps={{ input: { "aria-label": "选择全部曲目" } }} /></TableCell> : null}<TableCell>曲目</TableCell><TableCell>曲师</TableCell><TableCell>分类</TableCell>{showSubmitter ? <TableCell>投稿人</TableCell> : null}<TableCell>备注</TableCell><TableCell align="right">操作</TableCell></TableRow></TableHead>
        <TableBody>{songs.map((song) => <TableRow key={song.id} hover selected={selectedIds?.has(song.id)}>{selectionEnabled ? <TableCell padding="checkbox"><Checkbox checked={selectedIds?.has(song.id) ?? false} onChange={() => onToggleSelection?.(song.id)} slotProps={{ input: { "aria-label": `选择 ${song.song_name}` } }} /></TableCell> : null}<TableCell><Typography sx={{ fontWeight: 650 }}>{song.song_name}</Typography><Typography variant="caption" color="text.secondary">#{song.id}</Typography></TableCell><TableCell>{song.artist}</TableCell><TableCell><Chip size="small" label={song.song_type} /></TableCell>{showSubmitter ? <TableCell>{song.submitter?.display_name || song.submitter?.user_code || "-"}</TableCell> : null}<TableCell sx={{ maxWidth: 280, overflowWrap: "anywhere" }}>{song.remark || "-"}</TableCell><TableCell align="right"><Tooltip title="编辑"><IconButton size="small" onClick={() => onEdit(song)}><Pencil size={16} /></IconButton></Tooltip><Tooltip title="删除"><IconButton size="small" color="error" onClick={() => onDelete(song)}><Trash2 size={16} /></IconButton></Tooltip></TableCell></TableRow>)}</TableBody>
      </Table>
    </TableContainer>
  );
}


export function SongDialog({ song, onClose, onSave }: { song: SongRead | null; onClose: () => void; onSave: (payload: SongPayload) => Promise<void> }) {
  const [form, setForm] = useState<SongPayload>(EMPTY_SONG);
  const [error, setError] = useState("");
  useEffect(() => { if (song) setForm({ song_name: song.song_name, artist: song.artist, song_type: song.song_type, remark: song.remark }); }, [song]);
  return <Dialog open={Boolean(song)} onClose={onClose} fullWidth maxWidth="sm"><DialogTitle>编辑曲目</DialogTitle><DialogContent><Stack spacing={2} sx={{ pt: 1 }}><TextField label="曲名" value={form.song_name} onChange={(e) => setForm({ ...form, song_name: e.target.value })} /><TextField label="曲师" value={form.artist} onChange={(e) => setForm({ ...form, artist: e.target.value })} /><FormControl><InputLabel>分类</InputLabel><Select label="分类" value={form.song_type} onChange={(e) => setForm({ ...form, song_type: e.target.value })}><MenuItem value="A">A</MenuItem><MenuItem value="B">B</MenuItem><MenuItem value="C">C</MenuItem></Select></FormControl><TextField label="备注" multiline minRows={2} value={form.remark} onChange={(e) => setForm({ ...form, remark: e.target.value })} />{error ? <Alert severity="error">{error}</Alert> : null}</Stack></DialogContent><DialogActions><Button onClick={onClose}>取消</Button><Button variant="contained" startIcon={<Save size={16} />} onClick={() => void onSave(form).catch((err) => setError(err instanceof Error ? err.message : "保存失败"))}>保存</Button></DialogActions></Dialog>;
}


export { EMPTY_SONG };

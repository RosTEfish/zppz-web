import { useState } from "react";
import { Alert, Button, Snackbar, Stack } from "@mui/material";
import { FileDown, FileUp, Trash2 } from "lucide-react";
import { api, type SongRead } from "../../api/v1";
import { ResourceState, useApiResource } from "../../components/PagePrimitives";
import { queryKeys } from "../../api/queryKeys";
import { SongDialog, SongTable } from "../../components/SongComponents";
import { BatchDeleteDialog } from "./AdminShared";

export default function AdminSongs() {
  const songs = useApiResource(queryKeys.songs.admin, api.adminSongs);
  const [editing, setEditing] = useState<SongRead | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function importCsv(file?: File) { if (!file) return; try { const result = await api.importSongs(file); setMessage(result.message); await songs.reload(); } catch (err) { setError(err instanceof Error ? err.message : "导入失败"); } }
  async function remove(song: SongRead) { if (!window.confirm(`确认删除《${song.song_name}》？`)) return; try { await api.deleteAdminSong(song.id); setSelected((current) => { const next = new Set(current); next.delete(song.id); return next; }); songs.updateData((items) => items.filter((item) => item.id !== song.id)); } catch (err) { setError(err instanceof Error ? err.message : "删除失败"); } }
  async function removeSelected() { setDeleting(true); setError(""); try { const result = await api.batchDeleteAdminSongs([...selected]); setMessage(result.message); songs.updateData((items) => items.filter((item) => !selected.has(item.id))); setSelected(new Set()); setDeleteOpen(false); } catch (err) { setError(err instanceof Error ? err.message : "批量删除失败"); setDeleteOpen(false); } finally { setDeleting(false); } }
  function toggleSelection(songId: number) { setSelected((current) => { const next = new Set(current); if (next.has(songId)) next.delete(songId); else next.add(songId); return next; }); }
  return <Stack spacing={2}><Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}><Button variant="outlined" startIcon={<FileDown size={17} />} onClick={() => void api.exportSongs().catch((err) => setError(err.message))}>导出 CSV</Button><Button component="label" variant="contained" startIcon={<FileUp size={17} />}>导入 CSV<input hidden type="file" accept=".csv,text/csv" onChange={(event) => { void importCsv(event.target.files?.[0]); event.currentTarget.value = ""; }} /></Button><Button color="error" variant="outlined" startIcon={<Trash2 size={17} />} disabled={!selected.size} onClick={() => setDeleteOpen(true)}>删除 {selected.size} 项</Button></Stack>{error ? <Alert severity="error">{error}</Alert> : null}<ResourceState loading={songs.loading} error={songs.error} empty={!songs.data?.length ? "曲池为空" : undefined} />{songs.data?.length ? <SongTable songs={songs.data} showSubmitter onEdit={setEditing} onDelete={remove} selectedIds={selected} onToggleSelection={toggleSelection} onToggleAll={(checked) => setSelected(checked ? new Set(songs.data?.map((song) => song.id)) : new Set())} /> : null}<SongDialog song={editing} onClose={() => setEditing(null)} onSave={async (payload) => { if (!editing) return; const updated = await api.updateSong(editing.id, payload); songs.updateData((items) => items.map((item) => item.id === updated.id ? updated : item)); setEditing(null); }} /><BatchDeleteDialog open={deleteOpen} count={selected.size} label="首曲目" busy={deleting} onClose={() => setDeleteOpen(false)} onConfirm={() => void removeSelected()} /><Snackbar open={Boolean(message)} autoHideDuration={3000} onClose={() => setMessage("")} message={message} /></Stack>;
}

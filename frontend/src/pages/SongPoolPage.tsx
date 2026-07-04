import { type FormEvent, useState } from "react";
import { Alert, Box, Button, FormControl, InputLabel, MenuItem, Paper, Select, Snackbar, Stack, TextField } from "@mui/material";
import { Music2, Plus } from "lucide-react";
import { api, type SongPayload, type SongRead } from "../api/v1";
import { PageHeader, ResourceState, useResource } from "../components/PagePrimitives";
import { EMPTY_SONG, SongDialog, SongTable } from "../components/SongComponents";
import { useAuth } from "../contexts/AuthContext";
import { useConfig } from "../contexts/ConfigContext";


export default function SongPoolPage() {
  const songs = useResource(api.mySongs, []);
  const [form, setForm] = useState<SongPayload>(EMPTY_SONG);
  const [editing, setEditing] = useState<SongRead | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const { event } = useConfig();
  const { user } = useAuth();
  const limit = user?.identity === "participant" ? event?.settings.participant_song_limit : event?.settings.audience_song_limit;

  async function createSong(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await api.createSong(form);
      setForm(EMPTY_SONG);
      setMessage("曲目已加入曲池");
      await songs.reload();
    } catch (err) { setError(err instanceof Error ? err.message : "保存失败"); }
  }

  async function remove(song: SongRead) {
    if (!window.confirm(`确认删除《${song.song_name}》？`)) return;
    try { await api.deleteSong(song.id); await songs.reload(); } catch (err) { setError(err instanceof Error ? err.message : "删除失败"); }
  }

  return (
    <Stack spacing={3}>
      <PageHeader icon={Music2} title="我的曲池" meta={`${songs.data?.length ?? 0} / ${limit ?? "-"} 首`} />
      <Paper component="form" onSubmit={createSong} variant="outlined" sx={{ p: 2 }}>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "2fr 1.4fr 120px 2fr auto" }, gap: 1.5, alignItems: "center" }}>
          <TextField size="small" label="曲名" value={form.song_name} onChange={(e) => setForm({ ...form, song_name: e.target.value })} required />
          <TextField size="small" label="曲师" value={form.artist} onChange={(e) => setForm({ ...form, artist: e.target.value })} required />
          <FormControl size="small"><InputLabel>分类</InputLabel><Select label="分类" value={form.song_type} onChange={(e) => setForm({ ...form, song_type: e.target.value })}><MenuItem value="A">A</MenuItem><MenuItem value="B">B</MenuItem><MenuItem value="C">C</MenuItem></Select></FormControl>
          <TextField size="small" label="备注" value={form.remark} onChange={(e) => setForm({ ...form, remark: e.target.value })} />
          <Button type="submit" variant="contained" startIcon={<Plus size={17} />}>添加</Button>
        </Box>
      </Paper>
      {error ? <Alert severity="error">{error}</Alert> : null}
      <ResourceState loading={songs.loading} error={songs.error} empty={!songs.data?.length ? "暂无曲目" : undefined} />
      {songs.data?.length ? <SongTable songs={songs.data} onEdit={setEditing} onDelete={remove} /> : null}
      <SongDialog song={editing} onClose={() => setEditing(null)} onSave={async (payload) => { if (!editing) return; await api.updateMySong(editing.id, payload); setEditing(null); await songs.reload(); }} />
      <Snackbar open={Boolean(message)} autoHideDuration={2500} onClose={() => setMessage("")} message={message} />
    </Stack>
  );
}

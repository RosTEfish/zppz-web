import { type FormEvent, useEffect, useRef, useState } from "react";
import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography } from "@mui/material";
import { useConfirm } from "material-ui-confirm";
import { useSnackbar } from "notistack";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Music2, Plus, Search } from "lucide-react";
import { api, type BanMatchRead, type SongRead } from "../api/v1";
import { BanCheckPanel, canSubmitWithBanCheck, useBanCheck } from "../components/BanCheckPanel";
import { PageHeader, ResourceState, useApiResource } from "../components/PagePrimitives";
import { queryKeys } from "../api/queryKeys";
import { SongDialog, SongTable } from "../components/SongComponents";
import { useAuth } from "../contexts/AuthContext";
import { useConfig } from "../contexts/ConfigContext";
import { songSchema, type SongFormValues } from "../forms/schemas";


export default function SongPoolPage() {
  const songs = useApiResource(queryKeys.songs.mine, api.mySongs);
  const [editing, setEditing] = useState<SongRead | null>(null);
  const confirm = useConfirm();
  const [error, setError] = useState("");
  const [incompleteOpen, setIncompleteOpen] = useState(false);
  const shownIncomplete = useRef(false);
  const wasComplete = useRef(false);
  const { event } = useConfig();
  const { user } = useAuth();
  const isGuest = user?.identity === "guest";
  const limit = isGuest ? 0 : user?.identity === "participant" ? event?.settings.participant_song_limit : event?.settings.audience_song_limit;
  const songCount = songs.data?.length ?? 0;
  const incomplete = !isGuest && songs.data !== null && limit !== undefined && songCount < limit;

  useEffect(() => {
    if (songs.data === null || limit === undefined) return;
    if (songCount >= limit) {
      wasComplete.current = true;
      return;
    }
    if (!shownIncomplete.current || wasComplete.current) {
      setIncompleteOpen(true);
      shownIncomplete.current = true;
      wasComplete.current = false;
    }
  }, [limit, songCount, songs.data]);

  async function remove(song: SongRead) {
    const result = await confirm({ title: "删除曲目", description: `确认删除《${song.song_name}》？此操作不可撤销。`, confirmationButtonProps: { color: "error" } });
    if (!result.confirmed) return;
    try { await api.deleteSong(song.id); await songs.reload(); } catch (err) { setError(err instanceof Error ? err.message : "删除失败"); }
  }

  return (
    <Stack spacing={3}>
      <PageHeader icon={Music2} title="我的曲池" meta={isGuest ? "访客身份不参与投曲" : `${songs.data?.length ?? 0} / ${limit ?? "-"} 首`} />
      {isGuest ? <Alert severity="info">访客可以正常浏览赛事和参与开放的互动，但不需要向曲池投曲，也不会参与曲目抽取。</Alert> : null}
      {incomplete ? <Alert severity="warning">曲池尚未投满，还需提交 {Math.max((limit ?? 0) - songCount, 0)} 首曲目后才能进入抽签阶段。</Alert> : null}
      {!isGuest ? <AddSongForm onAdded={() => songs.reload()} /> : null}
      {error ? <Alert severity="error">{error}</Alert> : null}
      <BanSearchPanel />
      <ResourceState loading={songs.loading} error={songs.error} empty={!songs.data?.length ? "暂无曲目" : undefined} />
      {songs.data?.length ? <SongTable songs={songs.data} onEdit={isGuest ? undefined : setEditing} onDelete={remove} /> : null}
      <SongDialog song={editing} onClose={() => setEditing(null)} onSave={async (payload) => { if (!editing) return; await api.updateMySong(editing.id, payload); setEditing(null); await songs.reload(); }} />
      <Dialog open={incompleteOpen && incomplete} onClose={() => setIncompleteOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>曲池尚未投递完成</DialogTitle>
        <DialogContent><Stack spacing={1.5}><Typography>当前已提交 {songCount} / {limit ?? 0} 首曲目。</Typography><Alert severity="info">还需提交 {Math.max((limit ?? 0) - songCount, 0)} 首，所有用户投满后才能开始抽签并开放投稿。</Alert></Stack></DialogContent>
        <DialogActions><Button variant="contained" onClick={() => setIncompleteOpen(false)}>继续投曲</Button></DialogActions>
      </Dialog>
    </Stack>
  );
}


function AddSongForm({ onAdded }: { onAdded: () => Promise<unknown> }) {
  const { enqueueSnackbar } = useSnackbar();
  const emptySongForm: SongFormValues = { song_name: "", artist: "", remark: "" };
  const { register, handleSubmit, reset, watch, formState: { errors, isSubmitting } } = useForm<SongFormValues>({ resolver: zodResolver(songSchema), defaultValues: emptySongForm });
  const [error, setError] = useState("");
  const banCheck = useBanCheck(watch("song_name"), watch("artist"));

  const createSong = handleSubmit(async (form) => {
    setError("");
    if (!canSubmitWithBanCheck(banCheck)) {
      setError(banCheck.result?.status === "exact" ? "该曲目已命中往届 Ban 曲，不能加入曲池" : "请等待查重完成，并确认疑似结果后再保存");
      return;
    }
    try {
      await api.createSong({ ...form, acknowledge_ban_warning: banCheck.acknowledged });
      reset(emptySongForm);
      enqueueSnackbar("曲目已加入曲池", { variant: "success" });
      await onAdded();
    } catch (err) { setError(err instanceof Error ? err.message : "保存失败"); }
  });

  return (
    <Paper component="form" onSubmit={createSong} variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={1.5}>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "2fr 1.4fr 2fr auto" }, gap: 1.5, alignItems: "center" }}>
          <TextField size="small" label="曲名" {...register("song_name")} error={Boolean(errors.song_name)} helperText={errors.song_name?.message} />
          <TextField size="small" label="曲师" {...register("artist")} error={Boolean(errors.artist)} helperText={errors.artist?.message} />
          <TextField size="small" label="备注" {...register("remark")} error={Boolean(errors.remark)} helperText={errors.remark?.message} />
          <Button type="submit" variant="contained" disabled={isSubmitting || !canSubmitWithBanCheck(banCheck)} startIcon={<Plus size={17} />}>添加</Button>
        </Box>
        <BanCheckPanel state={banCheck} />
        {error ? <Alert severity="error">{error}</Alert> : null}
      </Stack>
    </Paper>
  );
}


function BanSearchPanel() {
  const [title, setTitle] = useState("");
  const [artist, setArtist] = useState("");
  const [results, setResults] = useState<BanMatchRead[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function search(event: FormEvent) {
    event.preventDefault();
    if (title.trim().length + artist.trim().length < 2) {
      setError("至少输入两个字符后再搜索");
      setResults(null);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const response = await api.searchBan(title, artist);
      setResults(response.items);
    } catch (err) {
      setResults(null);
      setError(err instanceof Error ? err.message : "搜索失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Paper component="section" variant="outlined" sx={{ p: { xs: 2, md: 2.5 } }}>
      <Stack spacing={1.5}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}>
          <Box>
            <Typography variant="h3">查找往届 Ban 曲</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>可以只填曲名、只填曲师，也可以组合搜索；结果用于人工核对。</Typography>
          </Box>
          <Search size={20} aria-hidden="true" />
        </Stack>
        <Box component="form" onSubmit={search} sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr auto" }, gap: 1.5, alignItems: "center" }}>
          <TextField size="small" label="曲名" value={title} onChange={(event) => setTitle(event.target.value)} />
          <TextField size="small" label="曲师" value={artist} onChange={(event) => setArtist(event.target.value)} />
          <Button type="submit" variant="outlined" disabled={loading} startIcon={<Search size={16} />}>{loading ? "搜索中…" : "搜索"}</Button>
        </Box>
        {error ? <Alert severity="warning">{error}</Alert> : null}
        {results ? (results.length ? <TableContainer component={Paper} variant="outlined"><Table size="small"><TableHead><TableRow><TableCell>曲目</TableCell><TableCell>赛事届次</TableCell><TableCell>匹配</TableCell><TableCell>备注</TableCell></TableRow></TableHead><TableBody>{results.map((match) => <TableRow key={`${match.entry_id}-${match.match_type}`}><TableCell><Typography variant="body2" sx={{ fontWeight: 700 }}>{match.title}</Typography><Typography variant="caption" color="text.secondary">{match.artist}</Typography></TableCell><TableCell>{match.round}</TableCell><TableCell><Chip size="small" color={match.match_type === "exact" ? "error" : "warning"} label={match.match_type === "exact" ? "精确匹配" : `疑似 ${match.score?.toFixed(1) ?? "-"}%`} /><Typography component="div" variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>{match.reason}</Typography></TableCell><TableCell sx={{ maxWidth: 260, overflowWrap: "anywhere" }}>{match.note || "-"}</TableCell></TableRow>)}</TableBody></Table></TableContainer> : <Alert severity="success">没有找到相近的往届 Ban 曲。</Alert>) : null}
      </Stack>
    </Paper>
  );
}

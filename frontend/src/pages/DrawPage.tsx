import { useState } from "react";
import { Alert, Button, Stack } from "@mui/material";
import { Sparkles } from "lucide-react";
import { api } from "../api/v1";
import { DrawList } from "../components/DrawList";
import { PageHeader, ResourceState, useResource } from "../components/PagePrimitives";
import { useAuth } from "../contexts/AuthContext";
import { useConfig } from "../contexts/ConfigContext";


export default function DrawPage() {
  const draws = useResource(api.myDraw, []);
  const { user } = useAuth();
  const { event } = useConfig();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function run() {
    setBusy(true); setError("");
    try { draws.setData(await api.drawMine()); } catch (err) { setError(err instanceof Error ? err.message : "抽签失败"); } finally { setBusy(false); }
  }
  return <Stack spacing={3}><PageHeader icon={Sparkles} title="我的抽签" meta={user?.identity === "participant" ? `应抽 ${event?.settings.draw_songs_per_participant ?? "-"} 首` : "当前账号不参与抽签"} actions={user?.identity === "participant" ? <Button variant="contained" startIcon={<Sparkles size={17} />} disabled={busy || event?.settings.submissions_open} onClick={() => void run()}>{draws.data?.length ? "重新抽签" : "开始抽签"}</Button> : undefined} />{event?.settings.submissions_open ? <Alert severity="info">投稿已开放，抽签结果已锁定。</Alert> : null}{error ? <Alert severity="error">{error}</Alert> : null}<ResourceState loading={draws.loading} error={draws.error} empty={!draws.data?.length ? "暂无抽签结果" : undefined} />{draws.data?.length ? <DrawList rows={draws.data} showAssignee={false} /> : null}</Stack>;
}

import { useState } from "react";
import { Alert, Button, Stack } from "@mui/material";
import { RefreshCw } from "lucide-react";
import { api } from "../../api/v1";
import { DrawList } from "../../components/DrawList";
import { ResourceState, useApiResource } from "../../components/PagePrimitives";
import { queryKeys } from "../../api/queryKeys";
import { useConfirm } from "material-ui-confirm";

export default function AdminDraw() {
  const rows = useApiResource(queryKeys.draws.admin, api.adminDrawResults);
  const stats = useApiResource(queryKeys.draws.stats, api.adminDrawStats);
  const confirm = useConfirm();
  const [error, setError] = useState("");
  async function run() { const result = await confirm({ title: "执行全局曲目分配", description: "已有完整分配会直接复用；仅在首次 Stage1 投稿前允许重新分配。", confirmationButtonProps: { color: "warning" } }); if (!result.confirmed) return; try { rows.setData(await api.runDraw()); await stats.reload(); } catch (err) { setError(err instanceof Error ? err.message : "全局分配失败"); } }
  const canRedraw = stats.data?.can_redraw ?? false;
  return <Stack spacing={2}><Button variant="contained" startIcon={<RefreshCw size={17} />} disabled={!canRedraw || rows.loading || stats.loading} onClick={() => void run()} sx={{ alignSelf: "flex-start" }}>执行全局分配 / 重新分配</Button>{stats.data && !stats.data.can_redraw ? <Alert severity="info">当前不在首次 Stage1 投稿前，或已有投稿；全局分配/重分配按钮已禁用。</Alert> : null}{error ? <Alert severity="error">{error}</Alert> : null}<ResourceState loading={rows.loading} error={rows.error} empty={!rows.data?.length ? "暂无曲目分配结果" : undefined} />{rows.data?.length ? <DrawList rows={rows.data} /> : null}</Stack>;
}

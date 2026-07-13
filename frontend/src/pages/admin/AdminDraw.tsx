import { useState } from "react";
import { Alert, Button, Stack } from "@mui/material";
import { RefreshCw } from "lucide-react";
import { api } from "../../api/v1";
import { DrawList } from "../../components/DrawList";
import { ResourceState, useResource } from "../../components/PagePrimitives";

export default function AdminDraw() {
  const rows = useResource(api.adminDrawResults, []);
  const [error, setError] = useState("");
  async function run() { if (!window.confirm("确认清空并重建全部抽签结果？")) return; try { rows.setData(await api.runDraw()); } catch (err) { setError(err instanceof Error ? err.message : "抽签失败"); } }
  return <Stack spacing={2}><Button variant="contained" startIcon={<RefreshCw size={17} />} onClick={() => void run()} sx={{ alignSelf: "flex-start" }}>全局重新抽签</Button>{error ? <Alert severity="error">{error}</Alert> : null}<ResourceState loading={rows.loading} error={rows.error} empty={!rows.data?.length ? "暂无抽签结果" : undefined} />{rows.data?.length ? <DrawList rows={rows.data} /> : null}</Stack>;
}

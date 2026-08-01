import { Alert, Stack } from "@mui/material";
import { Sparkles } from "lucide-react";
import { api, type SwapMeRead } from "../api/v1";
import { DrawList } from "../components/DrawList";
import Stage2SwapPanel from "../components/Stage2SwapPanel";
import { PageHeader, ResourceState, useApiResource } from "../components/PagePrimitives";
import { queryKeys } from "../api/queryKeys";
import { useAuth } from "../contexts/AuthContext";
import { useConfig } from "../contexts/ConfigContext";

export default function DrawPage() {
  const draws = useApiResource(queryKeys.draws.mine, api.myDraw);
  const { user } = useAuth();
  const { event } = useConfig();

  return (
    <Stack spacing={3}>
      <PageHeader
        icon={Sparkles}
        title="我的曲目"
        meta={user?.identity === "participant" ? `初始分配 ${event?.settings.draw_songs_per_participant ?? "-"} 首；Stage2 可继续换曲` : "当前账号不参与曲目分配"}
      />
      <Alert severity="info">曲目分配由赛事在报名结束后统一完成。此页面只展示当前有效曲目；Stage2 结束前，参赛者可以把不满意的曲目投回曲池并即时重新抽取。</Alert>
      <ResourceState loading={draws.loading} error={draws.error} empty={!draws.data?.length ? "暂无曲目分配结果" : undefined} />
      {draws.data?.length ? <DrawList rows={draws.data} showAssignee={false} /> : null}
      {user?.identity === "participant" ? <Stage2SwapPanel onUpdated={(next: SwapMeRead) => draws.setData(next.assignments)} /> : null}
    </Stack>
  );
}

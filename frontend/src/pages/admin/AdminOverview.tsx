import { Box, Paper, Typography } from "@mui/material";
import { api } from "../../api/v1";
import { ResourceState, useApiResource } from "../../components/PagePrimitives";
import { queryKeys } from "../../api/queryKeys";

export default function AdminOverview() {
  const stats = useApiResource(queryKeys.admin.overview, api.siteStats);
  const labels: Record<string, string> = { users: "用户", songs: "曲目", assignments: "抽签结果", submissions: "投稿", guess_charts: "谱面", charts: "谱面" };
  return <><ResourceState loading={stats.loading} error={stats.error} loadingVariant="cards" />{stats.data ? <Box sx={{ display: "grid", gridTemplateColumns: { xs: "repeat(2, 1fr)", lg: "repeat(4, 1fr)" }, gap: 2 }}>{Object.entries(stats.data).map(([key, value]) => <Paper key={key} variant="outlined" sx={{ p: 2.5 }}><Typography variant="body2" color="text.secondary">{labels[key] || key}</Typography><Typography variant="h1" sx={{ mt: 1 }}>{value}</Typography></Paper>)}</Box> : null}</>;
}

import { Box, Paper, Skeleton, Stack } from "@mui/material";

const phaseSlots = [0, 1, 2, 3, 4, 5];
const cardSlots = [0, 1, 2, 3];

export default function HomePageSkeleton() {
  return (
    <Stack spacing={3} aria-busy="true" aria-label="正在加载赛事内容">
      <Paper sx={{ p: { xs: 2.5, md: 4 }, minHeight: { xs: 292, md: 246 }, borderLeft: 5, borderColor: "primary.main" }}>
        <Skeleton variant="text" width={112} height={18} />
        <Skeleton variant="text" width="62%" height={52} sx={{ mt: 0.5 }} />
        <Skeleton variant="rounded" width="56%" height={32} sx={{ mt: 1.5 }} />
        <Skeleton variant="text" width="88%" height={24} sx={{ mt: 1 }} />
        <Stack direction="row" spacing={1} sx={{ mt: 2.5 }}>
          <Skeleton variant="rounded" width={112} height={40} />
          <Skeleton variant="rounded" width={112} height={40} />
          <Skeleton variant="rounded" width={112} height={40} />
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: { xs: 1.5, sm: 2 }, minHeight: { xs: 142, sm: 116 } }}>
        <Skeleton variant="text" width={180} height={18} />
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "repeat(2, minmax(0, 1fr))", sm: "repeat(6, minmax(90px, 1fr))" }, gap: 1, mt: 1 }}>
          {phaseSlots.map((slot) => (
            <Box key={slot} sx={{ minWidth: 0 }}>
              <Skeleton variant="rounded" height={slot < 2 ? 5 : 3} />
              <Skeleton variant="text" width="72%" height={18} sx={{ mt: 0.25 }} />
              <Skeleton variant="text" width="88%" height={16} />
            </Box>
          ))}
        </Box>
      </Paper>

      <Skeleton variant="rounded" height={56} />

      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", lg: "repeat(4, minmax(0, 1fr))" }, gap: 2 }}>
        {cardSlots.map((slot) => (
          <Paper key={slot} variant="outlined" sx={{ p: 2.5, minHeight: 132 }}>
            <Stack direction="row" sx={{ justifyContent: "space-between" }}>
              <Skeleton variant="circular" width={24} height={24} />
              <Skeleton variant="circular" width={18} height={18} />
            </Stack>
            <Skeleton variant="text" width="48%" height={28} sx={{ mt: 2 }} />
            <Skeleton variant="text" width="78%" height={20} sx={{ mt: 0.5 }} />
          </Paper>
        ))}
      </Box>
    </Stack>
  );
}

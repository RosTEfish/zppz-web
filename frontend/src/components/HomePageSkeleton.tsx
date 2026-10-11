import { Box, Skeleton, Stack } from "@mui/material";

const phaseSlots = [0, 1, 2, 3, 4];
const cardSlots = [0, 1, 2, 3, 4];

export default function HomePageSkeleton() {
  return (
    <Box aria-busy="true" aria-label="正在加载赛事内容">
      <Box sx={{ position: "relative", minHeight: { xs: "70vh", md: 520 }, px: { xs: 2.5, md: 8 }, py: 8, bgcolor: "#F4F6F5" }}>
        <Skeleton variant="text" width={160} height={40} />
        <Skeleton variant="text" width={72} height={20} sx={{ mt: 1 }} />
        <Skeleton variant="text" width="48%" height={64} sx={{ mt: 3 }} />
        <Skeleton variant="text" width="36%" height={28} sx={{ mt: 2 }} />
        <Stack direction="row" spacing={2} sx={{ mt: 4 }}>
          <Skeleton variant="rounded" width={140} height={48} />
          <Skeleton variant="rounded" width={100} height={48} />
        </Stack>
      </Box>
      <Box sx={{ maxWidth: 1280, mx: "auto", px: { xs: 2.5, md: 8 }, py: 6 }}>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "1fr 2fr" }, gap: 4, mb: 6 }}>
          <Skeleton variant="rounded" height={160} />
          <Box>
            <Skeleton variant="text" width={140} height={32} />
            <Box sx={{ display: "grid", gridTemplateColumns: `repeat(${phaseSlots.length}, minmax(0, 1fr))`, gap: 1, mt: 2 }}>
              {phaseSlots.map((slot) => (
                <Skeleton key={slot} variant="rounded" height={64} />
              ))}
            </Box>
          </Box>
        </Box>
        <Skeleton variant="text" width={120} height={32} sx={{ mb: 2 }} />
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", lg: "repeat(3, 1fr)" }, gap: 2 }}>
          {cardSlots.map((slot) => (
            <Skeleton key={slot} variant="rounded" height={140} />
          ))}
        </Box>
      </Box>
    </Box>
  );
}

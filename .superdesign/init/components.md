# Shared UI components

## PagePrimitives.tsx — `frontend/src/components/PagePrimitives.tsx`

Exports: `useApiResource`, `LoadingBlock`, `TableSkeleton`, `CardGridSkeleton`, `PageHeader`, `ResourceState`

```tsx
export function PageHeader({ icon: Icon, title, meta, actions }) {
  return (
    <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ mb: 3, alignItems: { xs: "stretch", sm: "center" }, justifyContent: "space-between" }}>
      <Stack direction="row" spacing={1.5} sx={{ minWidth: 0, alignItems: "center" }}>
        <Box sx={{ width: 42, height: 42, borderRadius: 1, bgcolor: "primary.light", color: "primary.dark", display: "grid", placeItems: "center", flexShrink: 0 }}><Icon size={22} /></Box>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h2">{title}</Typography>
          {meta ? <Typography variant="body2" color="text.secondary">{meta}</Typography> : null}
        </Box>
      </Stack>
      {actions ? <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>{actions}</Stack> : null}
    </Stack>
  );
}
```

## EventPhaseStatus.tsx — `frontend/src/components/EventPhaseStatus.tsx`

Exports: `PHASE_LABELS`, `PhaseHeadline`, `PhaseTimeline`, `formatCountdown`, `phaseStatusLabel`

Key UI: horizontal phase timeline with active gold dot glow; headline chip + countdown.

## HomePageSkeleton.tsx — `frontend/src/components/HomePageSkeleton.tsx`

Loading skeleton for home route.

## AnnouncementDialog.tsx — `frontend/src/components/AnnouncementDialog.tsx`

Markdown announcement modal from app shell.

## ChartPreviewDialog.tsx — `frontend/src/components/ChartPreviewDialog.tsx`

Majdata chart preview embed.

## DownloadPreparationDialog.tsx — `frontend/src/components/DownloadPreparationDialog.tsx`

Batch download progress dialog.

# Page dependency trees

## / (HomePage)

Entry: `frontend/src/pages/HomePage.tsx`

```
HomePage
├── contexts/useConfig → event, phases, guessGameAvailable, loading
├── contexts/useAuth → user, isLoggedIn, isAdmin, isPoolEditor
├── components/HomePageSkeleton
├── components/EventPhaseStatus
│   ├── PhaseHeadline
│   └── PhaseTimeline
├── lucide-react icons
└── @mui/material (Alert, Box, Button, Card, Paper, Stack, Typography)
```

## /guess (GuessPage)

Entry: `frontend/src/pages/GuessPage.tsx`

```
GuessPage
├── components/PagePrimitives (PageHeader, ResourceState, useApiResource)
├── components/ChartPreviewDialog
├── components/DownloadPreparationDialog
├── local: GuessFilterPanel, LoveVoteQuotaPanel, GuessChartCard, GuessDetailDialog
├── contexts/useAuth, useConfig
├── api/v1 guess endpoints
└── @mui/material (extensive)
```

## /login (AuthPage)

Entry: `frontend/src/pages/AuthPage.tsx`

```
AuthPage
├── contexts/useAuth, useConfig
├── components/EventPhaseStatus/isRegistrationClosed
├── forms/schemas authSchema (zod)
├── react-hook-form
└── @mui/material form controls
```

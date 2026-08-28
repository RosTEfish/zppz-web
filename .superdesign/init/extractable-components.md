# Extractable components catalog

## Layout

### AppShell
- Source: `frontend/src/App.tsx`
- Category: layout
- Props: mobile, drawerOpen, event, phases, user, links
- Hardcoded: Z brand mark, nav labels, drawer width 248

### SiteFooter
- Source: `frontend/src/App.tsx`
- Category: layout
- Hardcoded: ICP + 公安备案 links

## Basic

### PageHeader
- Source: `frontend/src/components/PagePrimitives.tsx`
- Category: basic
- Props: icon, title, meta?, actions?

### PhaseHeadline / PhaseTimeline
- Source: `frontend/src/components/EventPhaseStatus.tsx`
- Category: basic
- Props: phases

### ResourceState
- Source: `frontend/src/components/PagePrimitives.tsx`
- Category: basic
- Props: loading, error, empty?, loadingVariant

## Page-specific (high redesign value)

### HomeHero
- Source: `frontend/src/pages/HomePage.tsx` (Paper hero block)
- Category: basic

### StageNavCard
- Source: `frontend/src/pages/HomePage.tsx` (Card grid)
- Category: basic

### AuthFormCard
- Source: `frontend/src/pages/AuthPage.tsx`
- Category: basic

### GuessFilterPanel / GuessChartCard
- Source: `frontend/src/pages/GuessPage.tsx`
- Category: basic

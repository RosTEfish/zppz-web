# Page dependency trees

Candidate `--context-file` sets for design work. Local imports only (skip `node_modules`). Trace depth includes shared API/identity leaves used by auth/config.

---

## /login (AuthPage)

Entry: `frontend/src/pages/AuthPage.tsx`  
Layout: AppShell with `authLayout` (no page padding, no footer). Still under AppBar + Drawer.

**Current UI note:** Immersive full-bleed stage (`post` → `brand` → `hero`) + centered glass form. User finds this ugly — prefer design drafts before implementing.

Dependencies:

```
frontend/src/pages/AuthPage.tsx
- frontend/src/components/EventPhaseStatus.tsx
  - frontend/src/api/v1.ts
- frontend/src/contexts/AuthContext.tsx
  - frontend/src/api/v1.ts
  - frontend/src/api/queryKeys.ts
  - frontend/src/identity.ts
- frontend/src/contexts/ConfigContext.tsx
  - frontend/src/api/v1.ts
  - frontend/src/api/queryKeys.ts
- frontend/src/contexts/EventThemeProvider.tsx
  - frontend/src/hooks/useEventBackgrounds.ts
    - frontend/src/api/v1.ts
    - frontend/src/api/queryKeys.ts
    - frontend/src/components/PagePrimitives.tsx
    - frontend/src/contexts/ConfigContext.tsx
    - frontend/src/utils/backgroundAssets.ts
  - frontend/src/theme.ts
    - frontend/src/utils/extractImagePalette.ts
      - frontend/src/utils/colorMath.ts
    - frontend/src/utils/colorMath.ts
  - frontend/src/utils/extractImagePalette.ts
    - frontend/src/utils/colorMath.ts
- frontend/src/forms/schemas.ts
- frontend/src/hooks/useEventBackgrounds.ts
  - (same tree as under EventThemeProvider)
```

**Also useful for drafts (shell, not imported by AuthPage):**
- `frontend/src/App.tsx` — authLayout branch, AppBar, Drawer
- `frontend/src/index.css` — canvas washes / CSS vars
- `frontend/DESIGN.md` / `.superdesign/design-system.md`

---

## / (HomePage)

Entry: `frontend/src/pages/HomePage.tsx`  
Layout: AppShell padded main + `SiteFooter` when homepage ready. Props: `onOpenAnnouncement` from AppShell.

Dependencies:

```
frontend/src/pages/HomePage.tsx
- frontend/src/components/EventPhaseStatus.tsx
  - frontend/src/api/v1.ts
- frontend/src/components/EventHeroArt.tsx
  - frontend/src/contexts/EventThemeProvider.tsx
    - frontend/src/hooks/useEventBackgrounds.ts
      - frontend/src/api/v1.ts
      - frontend/src/api/queryKeys.ts
      - frontend/src/components/PagePrimitives.tsx
      - frontend/src/contexts/ConfigContext.tsx
      - frontend/src/utils/backgroundAssets.ts
    - frontend/src/theme.ts
      - frontend/src/utils/extractImagePalette.ts
        - frontend/src/utils/colorMath.ts
      - frontend/src/utils/colorMath.ts
    - frontend/src/utils/extractImagePalette.ts
  - frontend/src/utils/backgroundAssets.ts  (type BackgroundAsset)
- frontend/src/components/HomePageSkeleton.tsx
- frontend/src/contexts/AuthContext.tsx
  - frontend/src/api/v1.ts
  - frontend/src/api/queryKeys.ts
  - frontend/src/identity.ts
- frontend/src/contexts/ConfigContext.tsx
  - frontend/src/api/v1.ts
  - frontend/src/api/queryKeys.ts
- frontend/src/contexts/EventThemeProvider.tsx
  - (tree above)
- frontend/src/hooks/useEventBackgrounds.ts
  - (tree above)
```

**Also useful for drafts:**
- `frontend/src/App.tsx` — shell chrome around home
- `frontend/src/index.css`, `frontend/src/theme.ts`
- `.superdesign/design-system.md`

---

## Event art roles (both pages)

From `resolveBackgrounds` / DESIGN.md:

| Role | Typical files | Usage |
|---|---|---|
| `banner` | `*banner*` | Home hero first choice |
| `post` | `*post*` | Auth stage first; home fallback |
| `square` / brand | `*square*` | Brand / palette source, auth fallback |

API: `GET /api/v1/assets/backgrounds` (synced from repo `bg/`).

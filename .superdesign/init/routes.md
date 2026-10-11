# Routes — React Router (config in App.tsx)

**Router:** `react-router-dom` `BrowserRouter` + lazy-loaded page components.  
**Layout:** All routes render inside `AppShell` (AppBar + Drawer). `/login` uses `authLayout` (no content padding, no footer).  
**Guards:** `RequireLogin` → redirect `/login`; `RequireManager` → redirect `/`.

---

## Route table

| Path | Component | File | Layout / guard | Summary |
|---|---|---|---|---|
| `/` | `HomePage` | `frontend/src/pages/HomePage.tsx` | AppShell + padded main + footer (when ready) | Event hero, phase timeline, stage cards, next-action alert |
| `/login` | `AuthPage` | `frontend/src/pages/AuthPage.tsx` | AppShell + **authLayout** (full-bleed, no footer) | Immersive event art + glass login/register form |
| `/songs` | `SongPoolPage` | `frontend/src/pages/SongPoolPage.tsx` | RequireLogin | Song pool |
| `/banlist` | redirect | — | — | `Navigate` → `/songs?view=ban-check` |
| `/draw` | `DrawPage` | `frontend/src/pages/DrawPage.tsx` | RequireLogin | Draw / assignment |
| `/submissions` | `SubmissionPage` | `frontend/src/pages/SubmissionPage.tsx` | RequireLogin | Submissions upload |
| `/guess` | `GuessPage` | `frontend/src/pages/GuessPage.tsx` | AppShell (nav entry gated) | Guess / vote |
| `/archive` | `ArchivePage` | `frontend/src/pages/ArchivePage.tsx` | AppShell | Past events |
| `/account` | `AccountPage` | `frontend/src/pages/AccountPage.tsx` | RequireLogin | Account settings |
| `/admin/:tab` | `AdminPage` | `frontend/src/pages/AdminPage.tsx` | RequireManager | Admin workbench tabs |
| `/admin` | redirect | — | — | → `/admin/overview` |
| `*` | redirect | — | — | → `/` |

---

## Full Routes config (from App.tsx)

```tsx
<Suspense fallback={location.pathname === "/" ? <HomePageSkeleton /> : <LoadingBlock />}>
  <Routes>
    <Route path="/" element={<HomePage onOpenAnnouncement={openAnnouncement} />} />
    <Route path="/login" element={<AuthPage />} />
    <Route path="/songs" element={<RequireLogin><SongPoolPage /></RequireLogin>} />
    <Route path="/banlist" element={<Navigate to="/songs?view=ban-check" replace />} />
    <Route path="/draw" element={<RequireLogin><DrawPage /></RequireLogin>} />
    <Route path="/submissions" element={<RequireLogin><SubmissionPage /></RequireLogin>} />
    <Route path="/guess" element={<GuessPage />} />
    <Route path="/archive" element={<ArchivePage />} />
    <Route path="/account" element={<RequireLogin><AccountPage /></RequireLogin>} />
    <Route path="/admin/:tab" element={<RequireManager><AdminPage /></RequireManager>} />
    <Route path="/admin" element={<Navigate to="/admin/overview" replace />} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>
</Suspense>
```

---

## Lazy loaders

```tsx
const loadHomePage = () => import("./pages/HomePage");
const loadAuthPage = () => import("./pages/AuthPage");
const loadSongPoolPage = () => import("./pages/SongPoolPage");
const loadDrawPage = () => import("./pages/DrawPage");
const loadSubmissionPage = () => import("./pages/SubmissionPage");
const loadGuessPage = () => import("./pages/GuessPage");
const loadArchivePage = () => import("./pages/ArchivePage");
const loadAccountPage = () => import("./pages/AccountPage");
const loadAdminPage = async () => {
  const [page] = await preloadAdminPage(window.location.pathname);
  return page;
};
```

---

## Design targets (priority)

1. **`/login` (AuthPage)** — Current: immersive full-bleed `post|brand|hero` art + glass form. Product feedback: looks ugly; prefer **design drafts first** before code.
2. **`/` (HomePage)** — Hero event art from `/api/v1/assets/backgrounds` (`banner` → `post` → `square`), dynamic palette, stage cards.

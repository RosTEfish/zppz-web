# Routes — ZPPZ Arena

Router: `frontend/src/App.tsx` (React Router 7)

| Path | Component | Guard | Purpose |
|------|-----------|-------|---------|
| `/` | `pages/HomePage.tsx` | Public | Event hero, phase timeline, stage shortcuts |
| `/login` | `pages/AuthPage.tsx` | Public | Login / register |
| `/songs` | `pages/SongPoolPage.tsx` | RequireLogin | Song pool + ban check |
| `/banlist` | redirect | — | → `/songs?view=ban-check` |
| `/draw` | `pages/DrawPage.tsx` | RequireLogin | Drawn songs + Stage2 swap |
| `/submissions` | `pages/SubmissionPage.tsx` | RequireLogin | Chart uploads |
| `/guess` | `pages/GuessPage.tsx` | Public* | Guess/vote/browse charts |
| `/account` | `pages/AccountPage.tsx` | RequireLogin | Account settings |
| `/admin/:tab` | `pages/AdminPage.tsx` | RequireManager | Admin tabs |
| `/admin` | redirect | — | → `/admin/overview` |
| `*` | redirect | — | → `/` |

\* Guess nav shown when admin/pool_editor or `guessGameAvailable`.

## Admin tabs

`overview` · `settings` · `users` · `songs` · `draw` · `phases` · `submissions` · `guess` · `stats` · `banlist` · `webhooks`

## Design targets (phase 1 mockups)

1. `/` — HomePage
2. `/guess` — GuessPage
3. `/login` — AuthPage

Shell layout from `AppShell` in `App.tsx`: AppBar + Drawer (248px) + Container + SiteFooter.

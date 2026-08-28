# Layout components

## AppShell — `frontend/src/App.tsx`

Full app shell: SWRConfig → BrowserRouter → AuthProvider → ConfigProvider → AppShell.

Structure:
- Fixed AppBar (64px, glass blur)
- Drawer 248px (permanent desktop / temporary mobile)
- Main Container maxWidth xl
- SiteFooter with备案
- Lazy AnnouncementDialog

Nav links: 首页 `/` · 曲池 `/songs` · 曲目分配 `/draw` · 投稿 `/submissions` · 猜谱 `/guess` · 管理工作台 `/admin/*`

Brand block in drawer:
```tsx
<Box sx={{ width: 36, height: 36, borderRadius: 2, background: "linear-gradient(135deg, #176B52 0%, #0E523E 100%)" }}>Z</Box>
<Typography>ZPPZ Arena</Typography>
```

Selected nav style:
```tsx
borderLeft: "3px solid transparent"
"&.Mui-selected": { borderLeftColor: "primary.main", bgcolor: "rgba(23, 107, 82, 0.06)" }
```

## SiteFooter — inline in `App.tsx`

ICP + 公安备案 with beian icon.

## InteractionProviders — `frontend/src/components/InteractionProviders.tsx`

Snackbar + confirm dialog wrappers.

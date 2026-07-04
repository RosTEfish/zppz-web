import { useEffect, useMemo, useState } from "react";
import { Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, Stack, Tooltip, Typography } from "@mui/material";
import { Megaphone, X } from "lucide-react";
import { AnnouncementMarkdown } from "./AnnouncementMarkdown";


function announcementSignature(markdown: string) {
  let hash = 2166136261;
  for (let index = 0; index < markdown.length; index += 1) {
    hash ^= markdown.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `${markdown.length}:${(hash >>> 0).toString(36)}`;
}


export default function AnnouncementDialog({ eventId, markdown }: { eventId: number; markdown: string }) {
  const content = markdown.trim();
  const signature = useMemo(() => announcementSignature(content), [content]);
  const storageKey = `zppz:announcement:last-seen:${eventId}`;
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!content) {
      setOpen(false);
      return;
    }
    try {
      setOpen(window.localStorage.getItem(storageKey) !== signature);
    } catch {
      setOpen(true);
    }
  }, [content, signature, storageKey]);

  function acknowledge() {
    try {
      window.localStorage.setItem(storageKey, signature);
    } catch {
      // Private browsing can deny storage; closing should still work for this page view.
    }
    setOpen(false);
  }

  return (
    <Dialog open={open} onClose={acknowledge} fullWidth maxWidth="sm" scroll="paper" aria-labelledby="announcement-dialog-title">
      <DialogTitle id="announcement-dialog-title" sx={{ pr: 1.25 }}>
        <Stack direction="row" spacing={1.25} sx={{ alignItems: "center" }}>
          <Box sx={{ width: 36, height: 36, display: "grid", placeItems: "center", bgcolor: "primary.main", color: "primary.contrastText", borderRadius: 1 }}><Megaphone size={19} /></Box>
          <Typography component="span" variant="h3" sx={{ flex: 1 }}>赛事公告</Typography>
          <Tooltip title="关闭"><IconButton aria-label="关闭公告" onClick={acknowledge}><X size={19} /></IconButton></Tooltip>
        </Stack>
      </DialogTitle>
      <DialogContent dividers sx={{ py: 2.5 }}><AnnouncementMarkdown>{content}</AnnouncementMarkdown></DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}><Button variant="contained" onClick={acknowledge}>我知道了</Button></DialogActions>
    </Dialog>
  );
}

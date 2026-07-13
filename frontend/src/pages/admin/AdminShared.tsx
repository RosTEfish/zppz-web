import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle } from "@mui/material";
import { Trash2 } from "lucide-react";

export function BatchDeleteDialog({ open, count, label, busy, onClose, onConfirm }: { open: boolean; count: number; label: string; busy: boolean; onClose: () => void; onConfirm: () => void }) {
  return <Dialog open={open} onClose={busy ? undefined : onClose} fullWidth maxWidth="xs"><DialogTitle>确认批量删除</DialogTitle><DialogContent><Alert severity="warning">将删除选中的 {count} {label}。该操作无法撤销，任一项目不符合删除规则时整批都会取消。</Alert></DialogContent><DialogActions><Button disabled={busy} onClick={onClose}>取消</Button><Button color="error" variant="contained" startIcon={<Trash2 size={16} />} disabled={busy || !count} onClick={onConfirm}>{busy ? "删除中…" : "确认删除"}</Button></DialogActions></Dialog>;
}

import { useEffect, useRef } from "react";
import { Alert } from "@mui/material";
import { useConfirm } from "material-ui-confirm";

export function BatchDeleteDialog({ open, count, busy, label, onClose, onConfirm }: { open: boolean; count: number; label: string; busy: boolean; onClose: () => void; onConfirm: () => void }) {
  const confirm = useConfirm();
  const prompted = useRef(false);
  const onCloseRef = useRef(onClose);
  const onConfirmRef = useRef(onConfirm);
  onCloseRef.current = onClose;
  onConfirmRef.current = onConfirm;

  useEffect(() => {
    if (!open) {
      prompted.current = false;
      return;
    }
    if (busy || !count || prompted.current) return;
    prompted.current = true;
    let active = true;
    void confirm({
      title: "确认批量删除",
      content: <Alert severity="warning">将删除选中的 {count} {label}。该操作无法撤销；任一项目不符合删除规则时，整批操作都会取消。</Alert>,
      confirmationText: "确认删除",
      confirmationButtonProps: { color: "error", variant: "contained" },
    }).then((result) => {
      if (!active) return;
      if (result.confirmed) onConfirmRef.current();
      else onCloseRef.current();
    });
    return () => { active = false; };
  }, [busy, confirm, count, label, open]);

  return null;
}

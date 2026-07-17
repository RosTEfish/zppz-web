import { Dialog, DialogContent, DialogTitle, LinearProgress, Stack, Typography } from "@mui/material";
import { PackageOpen } from "lucide-react";


export function DownloadPreparationDialog({ open, count, unit }: { open: boolean; count: number; unit: string }) {
  return (
    <Dialog
      open={open}
      fullWidth
      maxWidth="xs"
      aria-labelledby="download-preparation-title"
      aria-describedby="download-preparation-description"
    >
      <DialogTitle id="download-preparation-title">
        <Stack direction="row" spacing={1.25} sx={{ alignItems: "center" }}>
          <PackageOpen size={21} aria-hidden="true" />
          <span>正在准备批量下载</span>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          <Typography id="download-preparation-description" color="text.secondary">
            服务器正在整理选中的 {count} {unit}并生成 ZIP。文件较多时可能需要一些时间，请勿重复点击或关闭页面。
          </Typography>
          <LinearProgress aria-label="正在准备下载文件" />
          <Typography variant="caption" color="text.secondary">
            准备完成后，下载会自动出现在浏览器的下载列表中。
          </Typography>
        </Stack>
      </DialogContent>
    </Dialog>
  );
}

import {
  Box,
  Chip,
  Divider,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import { formatTime, type DrawAssignmentRead } from "../api/v1";

export function DrawList({ rows, showAssignee = true }: { rows: DrawAssignmentRead[]; showAssignee?: boolean }) {
  const theme = useTheme();
  const mobile = useMediaQuery(theme.breakpoints.down("sm"));

  if (mobile) {
    return (
      <Stack spacing={1.25}>
        {rows.map((row) => (
          <Paper key={row.id} variant="outlined" sx={{ p: 2 }}>
            <Stack direction="row" sx={{ justifyContent: "space-between", gap: 1 }}>
              <Box>
                <Typography sx={{ fontWeight: 750 }}>{row.song.song_name}</Typography>
                <Typography variant="body2" color="text.secondary">{row.song.artist}</Typography>
              </Box>
              <Chip size="small" label={row.song.song_type} />
            </Stack>
            <Divider sx={{ my: 1.25 }} />
            <Stack spacing={0.5}>
              <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>
                备注：{row.song.remark || "-"}
              </Typography>
              {showAssignee ? (
                <Typography variant="body2">
                  被抽取人：{row.assigned_to.display_name || row.assigned_to.user_code}
                </Typography>
              ) : null}
              <Typography variant="caption" color="text.secondary">{formatTime(row.created_at)}</Typography>
            </Stack>
          </Paper>
        ))}
      </Stack>
    );
  }

  return (
    <TableContainer component={Paper} variant="outlined">
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>曲目</TableCell>
            <TableCell>曲师</TableCell>
            <TableCell>分类</TableCell>
            <TableCell>备注</TableCell>
            {showAssignee ? <TableCell>被抽取人</TableCell> : null}
            <TableCell>时间</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.id}>
              <TableCell sx={{ fontWeight: 650 }}>{row.song.song_name}</TableCell>
              <TableCell>{row.song.artist}</TableCell>
              <TableCell><Chip size="small" label={row.song.song_type} /></TableCell>
              <TableCell sx={{ maxWidth: 320, overflowWrap: "anywhere" }}>{row.song.remark || "-"}</TableCell>
              {showAssignee ? (
                <TableCell>{row.assigned_to.display_name || row.assigned_to.user_code}</TableCell>
              ) : null}
              <TableCell>{formatTime(row.created_at)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

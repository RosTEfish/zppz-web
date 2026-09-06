import { useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Switch,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";
import { KeyRound } from "lucide-react";
import { api, type UserRead } from "../../api/v1";
import { useAuth } from "../../contexts/AuthContext";
import { ResourceState, useApiResource } from "../../components/PagePrimitives";
import { queryKeys } from "../../api/queryKeys";
import { dataGridZhCN } from "../../components/dataGridLocale";

function updateRole(roles: string[], role: string, enabled: boolean): string[] {
  if (enabled) return roles.includes(role) ? roles : [...roles, role];
  return roles.filter((item) => item !== role);
}

function targetIsOwner(user: UserRead): boolean {
  return Boolean(user.is_owner || user.roles.includes("owner"));
}

function targetIsAdmin(user: UserRead): boolean {
  return targetIsOwner(user) || user.roles.includes("admin");
}

function resetDisabledReason(user: UserRead, actorIsOwner: boolean): string {
  if (targetIsOwner(user)) return "Owner 密码请在账号设置中自行修改";
  if (targetIsAdmin(user) && !actorIsOwner) return "只有 Owner 可以重置管理员密码";
  return "";
}

export default function AdminUsers() {
  const users = useApiResource(queryKeys.admin.users, api.users);
  const { isOwner } = useAuth();
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [resetTarget, setResetTarget] = useState<UserRead | null>(null);
  const [passwords, setPasswords] = useState({ next: "", confirm: "" });
  const [resetBusy, setResetBusy] = useState(false);
  const [resetError, setResetError] = useState("");

  async function change(user: UserRead, patch: Partial<{ identity: string; roles: string[]; display_name: string; is_active: boolean }>) {
    try {
      const updated = await api.updateUser(user.id, {
        identity: patch.identity ?? user.identity,
        roles: patch.roles ?? user.roles,
        display_name: patch.display_name ?? user.display_name,
        is_active: patch.is_active ?? user.is_active ?? true,
      });
      users.updateData((items) => items.map((item) => (item.id === updated.id ? updated : item)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    }
  }

  function openReset(user: UserRead) {
    setError("");
    setSuccess("");
    setResetError("");
    setPasswords({ next: "", confirm: "" });
    setResetTarget(user);
  }

  function closeReset() {
    if (resetBusy) return;
    setResetTarget(null);
    setPasswords({ next: "", confirm: "" });
    setResetError("");
  }

  async function submitReset() {
    if (!resetTarget) return;
    setResetError("");
    if (passwords.next.length < 6) {
      setResetError("密码至少 6 个字符");
      return;
    }
    if (passwords.next.length > 128) {
      setResetError("密码不能超过 128 个字符");
      return;
    }
    if (passwords.next !== passwords.confirm) {
      setResetError("两次输入的新密码不一致");
      return;
    }
    setResetBusy(true);
    try {
      const result = await api.resetPassword(resetTarget.id, passwords.next);
      setSuccess(result.message || `已重置 ${resetTarget.user_code} 的密码`);
      setResetTarget(null);
      setPasswords({ next: "", confirm: "" });
    } catch (err) {
      setResetError(err instanceof Error ? err.message : "重置失败");
    } finally {
      setResetBusy(false);
    }
  }

  const columns = useMemo<GridColDef<UserRead>[]>(
    () => [
      { field: "qq_id", headerName: "注册 QQ 号", width: 130, valueGetter: (value) => value || "-" },
      { field: "user_code", headerName: "账号", minWidth: 120, flex: 0.6 },
      {
        field: "display_name",
        headerName: "显示名",
        minWidth: 160,
        flex: 0.8,
        sortable: false,
        renderCell: ({ row }) => (
          <Box sx={{ display: "flex", alignItems: "center", width: "100%", height: "100%" }}>
            <TextField
              fullWidth
              size="small"
              defaultValue={row.display_name}
              slotProps={{ htmlInput: { "aria-label": `显示名 ${row.user_code}` } }}
              onBlur={(event) => {
                if (event.target.value !== row.display_name) void change(row, { display_name: event.target.value });
              }}
            />
          </Box>
        ),
      },
      {
        field: "identity",
        headerName: "身份",
        width: 120,
        renderCell: ({ row }) => (
          <Select
            size="small"
            value={row.identity}
            inputProps={{ "aria-label": `身份 ${row.user_code}` }}
            onChange={(event) => void change(row, { identity: event.target.value })}
          >
            <MenuItem value="participant">参赛者</MenuItem>
            <MenuItem value="audience">观众</MenuItem>
            <MenuItem value="guest">访客</MenuItem>
          </Select>
        ),
      },
      {
        field: "roles",
        headerName: "权限",
        minWidth: 190,
        flex: 0.8,
        sortable: false,
        filterable: false,
        renderCell: ({ row }) => {
          const owner = targetIsOwner(row);
          const admin = targetIsAdmin(row);
          return (
            <Stack spacing={0} sx={{ justifyContent: "center", height: "100%" }}>
              <FormControlLabel
                sx={{ m: 0 }}
                control={
                  <Checkbox
                    checked={admin}
                    disabled={owner || !isOwner}
                    onChange={(event) => void change(row, { roles: updateRole(row.roles, "admin", event.target.checked) })}
                  />
                }
                label="管理员"
              />
              {owner ? <Chip size="small" color="warning" label="Owner / 最高权限" /> : null}
              <FormControlLabel
                sx={{ m: 0 }}
                control={
                  <Checkbox
                    checked={row.roles.includes("pool_editor")}
                    onChange={(event) => void change(row, { roles: updateRole(row.roles, "pool_editor", event.target.checked) })}
                  />
                }
                label="曲池编辑"
              />
            </Stack>
          );
        },
      },
      {
        field: "is_active",
        headerName: "启用",
        width: 90,
        renderCell: ({ row }) => {
          const owner = targetIsOwner(row);
          const admin = targetIsAdmin(row);
          const disabled = owner || (admin && !isOwner);
          const title = owner
            ? "Owner 状态只能通过后端 CLI 更换"
            : admin && !isOwner
              ? "普通管理员不能启用或停用管理员账号"
              : "";
          return (
            <Tooltip title={title}>
              <span>
                <Switch
                  checked={row.is_active ?? true}
                  disabled={disabled}
                  slotProps={{ input: { "aria-label": `启用 ${row.user_code}` } }}
                  onChange={(event) => void change(row, { is_active: event.target.checked })}
                />
              </span>
            </Tooltip>
          );
        },
      },
      {
        field: "actions",
        headerName: "操作",
        width: 140,
        sortable: false,
        filterable: false,
        renderCell: ({ row }) => {
          const reason = resetDisabledReason(row, isOwner);
          return (
            <Tooltip title={reason}>
              <span>
                <Button
                  size="small"
                  startIcon={<KeyRound size={15} />}
                  disabled={Boolean(reason)}
                  onClick={() => openReset(row)}
                  aria-label={`重置密码 ${row.user_code}`}
                >
                  重置密码
                </Button>
              </span>
            </Tooltip>
          );
        },
      },
    ],
    [isOwner, users.updateData],
  );

  return (
    <>
      {error ? <Alert severity="error">{error}</Alert> : null}
      {success ? (
        <Alert severity="success" sx={{ mt: error ? 1 : 0 }}>
          {success}
        </Alert>
      ) : null}
      <ResourceState loading={users.loading} error={users.error} />
      {users.data ? (
        <Paper variant="outlined" sx={{ mt: 2, height: Math.min(720, 112 + users.data.length * 82), minHeight: 320 }}>
          <DataGrid
            rows={users.data}
            columns={columns}
            getRowId={(row) => row.id}
            getRowHeight={() => 82}
            disableRowSelectionOnClick
            initialState={{ pagination: { paginationModel: { page: 0, pageSize: 25 } } }}
            pageSizeOptions={[25, 50, 100]}
            localeText={dataGridZhCN}
            sx={{ border: 0 }}
          />
        </Paper>
      ) : null}
      <Dialog open={Boolean(resetTarget)} onClose={closeReset} fullWidth maxWidth="sm">
        <DialogTitle>重置账号密码</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Alert severity="warning">
              重置后，账号「{resetTarget?.user_code}」的所有登录会话将立即失效，对方需使用新密码重新登录。
            </Alert>
            <Typography variant="body2" color="text.secondary">
              显示名：{resetTarget?.display_name || "（未设置）"}
            </Typography>
            <TextField
              autoFocus
              fullWidth
              type="password"
              label="新密码"
              value={passwords.next}
              onChange={(event) => setPasswords((current) => ({ ...current, next: event.target.value }))}
              disabled={resetBusy}
              slotProps={{ htmlInput: { minLength: 6, maxLength: 128, "aria-label": "新密码" } }}
              helperText="至少 6 个字符"
              autoComplete="new-password"
            />
            <TextField
              fullWidth
              type="password"
              label="确认新密码"
              value={passwords.confirm}
              onChange={(event) => setPasswords((current) => ({ ...current, confirm: event.target.value }))}
              disabled={resetBusy}
              slotProps={{ htmlInput: { minLength: 6, maxLength: 128, "aria-label": "确认新密码" } }}
              autoComplete="new-password"
            />
            {resetError ? <Alert severity="error">{resetError}</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button disabled={resetBusy} onClick={closeReset}>
            取消
          </Button>
          <Button
            color="warning"
            variant="contained"
            disabled={resetBusy || !passwords.next || !passwords.confirm}
            onClick={() => void submitReset()}
            startIcon={resetBusy ? <CircularProgress size={16} color="inherit" /> : <KeyRound size={17} />}
          >
            {resetBusy ? "重置中…" : "确认重置"}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

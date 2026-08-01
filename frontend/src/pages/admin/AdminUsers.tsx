import { useMemo, useState } from "react";
import { Alert, Checkbox, Chip, FormControlLabel, MenuItem, Paper, Select, Stack, Switch, TextField, Tooltip } from "@mui/material";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";
import { api, type UserRead } from "../../api/v1";
import { useAuth } from "../../contexts/AuthContext";
import { ResourceState, useApiResource } from "../../components/PagePrimitives";
import { queryKeys } from "../../api/queryKeys";
import { dataGridZhCN } from "../../components/dataGridLocale";

function updateRole(roles: string[], role: string, enabled: boolean): string[] {
  if (enabled) return roles.includes(role) ? roles : [...roles, role];
  return roles.filter((item) => item !== role);
}

export default function AdminUsers() {
  const users = useApiResource(queryKeys.admin.users, api.users);
  const { isOwner } = useAuth();
  const [error, setError] = useState("");

  async function change(user: UserRead, patch: Partial<{ identity: string; roles: string[]; display_name: string; is_active: boolean }>) {
    try {
      const updated = await api.updateUser(user.id, { identity: patch.identity ?? user.identity, roles: patch.roles ?? user.roles, display_name: patch.display_name ?? user.display_name, is_active: patch.is_active ?? user.is_active ?? true });
      users.updateData((items) => items.map((item) => item.id === updated.id ? updated : item));
    } catch (err) { setError(err instanceof Error ? err.message : "保存失败"); }
  }

  const columns = useMemo<GridColDef<UserRead>[]>(() => [
    { field: "qq_id", headerName: "注册 QQ 号", width: 130, valueGetter: (value) => value || "-" },
    { field: "user_code", headerName: "账号", minWidth: 120, flex: 0.6 },
    { field: "display_name", headerName: "显示名", minWidth: 160, flex: 0.8, sortable: false, renderCell: ({ row }) => <TextField size="small" defaultValue={row.display_name} slotProps={{ htmlInput: { "aria-label": `显示名 ${row.user_code}` } }} onBlur={(event) => { if (event.target.value !== row.display_name) void change(row, { display_name: event.target.value }); }} /> },
    { field: "identity", headerName: "身份", width: 120, renderCell: ({ row }) => <Select size="small" value={row.identity} inputProps={{ "aria-label": `身份 ${row.user_code}` }} onChange={(event) => void change(row, { identity: event.target.value })}><MenuItem value="participant">参赛者</MenuItem><MenuItem value="audience">观众</MenuItem></Select> },
    { field: "roles", headerName: "权限", minWidth: 190, flex: 0.8, sortable: false, filterable: false, renderCell: ({ row }) => { const targetIsOwner = Boolean(row.is_owner || row.roles.includes("owner")); const targetIsAdmin = targetIsOwner || row.roles.includes("admin"); return <Stack spacing={0} sx={{ justifyContent: "center", height: "100%" }}><FormControlLabel sx={{ m: 0 }} control={<Checkbox checked={targetIsAdmin} disabled={targetIsOwner || !isOwner} onChange={(event) => void change(row, { roles: updateRole(row.roles, "admin", event.target.checked) })} />} label="管理员" />{targetIsOwner ? <Chip size="small" color="warning" label="Owner / 最高权限" /> : null}<FormControlLabel sx={{ m: 0 }} control={<Checkbox checked={row.roles.includes("pool_editor")} onChange={(event) => void change(row, { roles: updateRole(row.roles, "pool_editor", event.target.checked) })} />} label="曲池编辑" /></Stack>; } },
    { field: "is_active", headerName: "启用", width: 90, renderCell: ({ row }) => { const targetIsOwner = Boolean(row.is_owner || row.roles.includes("owner")); const targetIsAdmin = targetIsOwner || row.roles.includes("admin"); const disabled = targetIsOwner || (targetIsAdmin && !isOwner); const title = targetIsOwner ? "Owner 状态只能通过后端 CLI 更换" : targetIsAdmin && !isOwner ? "普通管理员不能启用或停用管理员账号" : ""; return <Tooltip title={title}><span><Switch checked={row.is_active ?? true} disabled={disabled} slotProps={{ input: { "aria-label": `启用 ${row.user_code}` } }} onChange={(event) => void change(row, { is_active: event.target.checked })} /></span></Tooltip>; } },
  ], [isOwner, users.updateData]);

  return <>{error ? <Alert severity="error">{error}</Alert> : null}<ResourceState loading={users.loading} error={users.error} />{users.data ? <Paper variant="outlined" sx={{ mt: 2, height: Math.min(720, 112 + users.data.length * 82), minHeight: 320 }}><DataGrid rows={users.data} columns={columns} getRowId={(row) => row.id} getRowHeight={() => 82} disableRowSelectionOnClick initialState={{ pagination: { paginationModel: { page: 0, pageSize: 25 } } }} pageSizeOptions={[25, 50, 100]} localeText={dataGridZhCN} sx={{ border: 0 }} /></Paper> : null}</>;
}

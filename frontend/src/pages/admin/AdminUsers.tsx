import { useState } from "react";
import {
  Alert,
  Checkbox,
  Chip,
  FormControlLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
} from "@mui/material";
import { api, type UserRead } from "../../api/v1";
import { useAuth } from "../../contexts/AuthContext";
import { ResourceState, useResource } from "../../components/PagePrimitives";

function updateRole(roles: string[], role: string, enabled: boolean): string[] {
  if (enabled) return roles.includes(role) ? roles : [...roles, role];
  return roles.filter((item) => item !== role);
}

export default function AdminUsers() {
  const users = useResource(api.users, []);
  const { isOwner } = useAuth();
  const [error, setError] = useState("");

  async function change(
    user: UserRead,
    patch: Partial<{ identity: string; roles: string[]; display_name: string; is_active: boolean }>,
  ) {
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

  return (
    <>
      {error ? <Alert severity="error">{error}</Alert> : null}
      <ResourceState loading={users.loading} error={users.error} />
      {users.data ? (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>账号</TableCell>
                <TableCell>显示名</TableCell>
                <TableCell>身份</TableCell>
                <TableCell>权限</TableCell>
                <TableCell>启用</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {users.data.map((user) => {
                const targetIsOwner = user.is_owner || user.roles.includes("owner");
                const targetIsAdmin = targetIsOwner || user.roles.includes("admin");
                const adminDisabled = targetIsOwner || !isOwner;
                const activeDisabled = targetIsOwner || (targetIsAdmin && !isOwner);
                const activeTooltip = targetIsOwner
                  ? "Owner 状态只能通过后端 CLI 更换"
                  : targetIsAdmin && !isOwner
                    ? "普通管理员不能启用或停用管理员账号"
                    : "";

                return (
                  <TableRow key={user.id}>
                    <TableCell>{user.user_code}</TableCell>
                    <TableCell>
                      <TextField
                        size="small"
                        defaultValue={user.display_name}
                        onBlur={(event) => {
                          if (event.target.value !== user.display_name) {
                            void change(user, { display_name: event.target.value });
                          }
                        }}
                      />
                    </TableCell>
                    <TableCell>
                      <Select
                        size="small"
                        value={user.identity}
                        onChange={(event) => void change(user, { identity: event.target.value })}
                      >
                        <MenuItem value="participant">参赛者</MenuItem>
                        <MenuItem value="audience">观众</MenuItem>
                      </Select>
                    </TableCell>
                    <TableCell>
                      <Stack spacing={0} sx={{ minWidth: 160 }}>
                        <FormControlLabel
                          sx={{ m: 0 }}
                          control={
                            <Checkbox
                              checked={targetIsAdmin}
                              disabled={adminDisabled}
                              onChange={(event) =>
                                void change(user, {
                                  roles: updateRole(user.roles, "admin", event.target.checked),
                                })
                              }
                            />
                          }
                          label="管理员"
                        />
                        {targetIsOwner ? <Chip size="small" color="warning" label="Owner / 最高权限" /> : null}
                        <FormControlLabel
                          sx={{ m: 0 }}
                          control={
                            <Checkbox
                              checked={user.roles.includes("pool_editor")}
                              onChange={(event) =>
                                void change(user, {
                                  roles: updateRole(user.roles, "pool_editor", event.target.checked),
                                })
                              }
                            />
                          }
                          label="曲池编辑"
                        />
                      </Stack>
                    </TableCell>
                    <TableCell>
                      <Tooltip title={activeTooltip}>
                        <span>
                          <Switch
                            checked={user.is_active ?? true}
                            disabled={activeDisabled}
                            onChange={(event) => void change(user, { is_active: event.target.checked })}
                          />
                        </span>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      ) : null}
    </>
  );
}

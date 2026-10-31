// Port, admin code, and password defaults must match scripts/e2e_server.sh.
// Event name and admin display name come from seed_defaults in backend/app/db/bootstrap.py.
export const e2ePort = process.env.E2E_PORT ?? "8765";
export const e2eBaseURL = process.env.E2E_BASE_URL ?? `http://127.0.0.1:${e2ePort}`;
export const e2eAdminCode = process.env.E2E_ADMIN_CODE ?? "admin";
export const e2eAdminPassword = process.env.E2E_ADMIN_PASSWORD ?? "e2e-admin-password";
export const seededEventName = "这谱谱这 #5";
export const seededAdminDisplayName = "赛事管理员";

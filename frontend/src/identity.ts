export type Identity = "participant" | "audience" | "guest";

export function identityLabel(identity?: string): string {
  if (identity === "participant") return "参赛者";
  if (identity === "audience") return "观众";
  if (identity === "guest") return "访客";
  return "未知身份";
}

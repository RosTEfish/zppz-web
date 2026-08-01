import { z } from "zod";

export const authSchema = z.object({
  mode: z.enum(["login", "register"]),
  user_code: z.string().trim().min(1, "请输入账号").max(64, "账号不能超过 64 个字符"),
  qq_id: z.string().trim().max(32, "QQ 不能超过 32 个字符"),
  password: z.string().min(1, "请输入密码").max(128, "密码不能超过 128 个字符"),
  identity: z.enum(["participant", "audience"]),
}).superRefine((value, context) => {
  if (value.mode !== "register") return;
  if (value.user_code.length < 2) context.addIssue({ code: "custom", path: ["user_code"], message: "账号至少 2 个字符" });
  if (!value.qq_id) context.addIssue({ code: "custom", path: ["qq_id"], message: "请输入 QQ" });
  if (value.password.length < 6) context.addIssue({ code: "custom", path: ["password"], message: "密码至少 6 个字符" });
});

export type AuthFormValues = z.infer<typeof authSchema>;

export const songSchema = z.object({
  song_name: z.string().trim().min(1, "请输入曲名").max(200, "曲名不能超过 200 个字符"),
  artist: z.string().trim().min(1, "请输入曲师").max(100, "曲师不能超过 100 个字符"),
  song_type: z.enum(["A", "B", "C"]).optional(),
  remark: z.string().max(500, "备注不能超过 500 个字符"),
});

export type SongFormValues = z.infer<typeof songSchema>;

export const chartSchema = z.object({
  title: z.string().trim().min(1, "请输入标题").max(200),
  author: z.string().trim().min(1, "请输入曲师").max(100),
  designer: z.string().trim().max(200),
  level: z.string().trim().min(1, "请输入等级").max(20),
  lane: z.enum(["normal", "j", "exhibition"]),
  guess_group_key: z.string(),
  is_self_selected: z.boolean(),
});

export type ChartFormValues = z.infer<typeof chartSchema>;

export const eventSettingsSchema = z.object({
  name: z.string().trim().min(1, "请输入赛事名称").max(200, "赛事名称不能超过 200 个字符"),
  participant_song_limit: z.number().int().min(0).max(50),
  audience_song_limit: z.number().int().min(0).max(50),
  draw_songs_per_participant: z.number().int().min(1).max(10),
  true_love_vote_limit_below_14: z.number().int().min(0).max(50),
  true_love_vote_limit_at_least_14: z.number().int().min(0).max(50),
  funny_vote_limit: z.number().int().min(0).max(50),
  announcement_text: z.string(),
});

export const resetConfirmationSchema = z.object({
  confirmation: z.string().refine((value) => value === "清除全部数据", "请输入完整确认词"),
});

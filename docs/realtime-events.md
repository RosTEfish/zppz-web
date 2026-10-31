# 全站 Server-Sent Events

浏览器通过一条 `GET /api/v1/events` 长连接接收领域事件，再用事件里的 `resources` 让 SWR 重新拉取对应缓存。投稿处理、赛事阶段、抽曲结果、猜谱状态和换曲都会走这条链路。原来投稿页和管理端投稿列表上的 3 秒轮询改成了事件驱动，并保留 60 秒的可见标签页兜底。

## 为什么用数据库 outbox，而不是 Redis 或 LISTEN/NOTIFY

生产默认是 SQLite，且 `WEB_CONCURRENCY=1`。投稿 worker、webhook worker 和 API 是不同进程，内存队列过不了进程边界。SQLite 也没有 `LISTEN/NOTIFY`。

引入 Redis，或者为了这条功能把生产库迁到 Postgres，都超出这次的范围。Compose 里的 Postgres 同样不需要 `LISTEN`：每个 API 进程自己按主键尾读同一张表，worker 把事件和业务写在同一个事务里。事务回滚时事件一起消失。

`domain_events` 只保留最新约 2000 行。API 流、投稿 worker 和 webhook worker 都会定期清理。webhook worker 今天写的是对外发布 outbox，不改页面上盯着的那些表；它加载同一个 Session 钩子，以后如果改到抽曲、猜谱、投稿任务或阶段，事件会自动出现。

## 事件

帧格式：

```
id: 42
event: submission.job
data: {"id":42,"topic":"submission.job","scope":"user","subject_user_id":7,"resources":["submissions"],"payload":{"jobs":[{"id":"...","status":"processing","stage":"validating"}]},"created_at":"..."}
```

| topic | scope | 谁能看到 | resources |
| --- | --- | --- | --- |
| `submission.job` | `user` | 任务所属用户，以及管理员 | `submissions` |
| `contest.updated` | `public` | 所有人，含未登录 | `contest` `guess` `draws` `swap` `submissions` `admin` |
| `draw.reveal` | `authenticated` | 已登录用户 | `draws` `swap` `admin` |
| `guess.state` | `public` | 所有人 | `guess` `contest` `admin` |
| `swap.updated` | `authenticated` | 已登录用户 | `swap` `draws` |

未带登录凭证时只推 `public`。带了 Cookie 或 `Authorization: Bearer` 但会话无效时返回 401，而不是悄悄降级成匿名流。前端按 `resources` 映射 SWR key。投稿任务还在 `queued` / `processing` 时只刷新任务列表；进入 `completed` / `failed` / `cancelled` 后再刷新投稿列表、bootstrap 和猜谱可用性。

首次连接不重放全表，只补最近 20 秒，避免刚打开页面时打出一串过期刷新。断线重连带 `after`（EventSource 的 `Last-Event-ID` 同样有效）。大约每 15 秒一条 `: keepalive`。流不可用时，前端每 15 秒重新校验仍在缓存里的领域 key；流正常时，每 60 秒只复查 bootstrap。

发布点是 SQLAlchemy 的 `before_flush` 钩子，挂在 `app.db.session` 导入时。任何走这个 Session 的进程都会写 outbox，不需要在每个提交点手工调用。

## Nginx

仓库里的 `infra/nginx/default.conf` 已经为 `location = /api/v1/events` 关闭了 `proxy_buffering` 和 `gzip`，并把读超时放到 3600 秒。镜像里的 Nginx 会带上这段配置。应用响应也带 `X-Accel-Buffering: no` 和 `Cache-Control: no-cache`。Starlette 的 GZip 中间件会跳过 `text/event-stream`。

生产 systemd 前面的宿主机 Nginx **不**由部署脚本覆盖。如果站点前面还有一层反代，需要运维在那层加上同样的 location，否则事件会被缓冲到缓冲写满才到达浏览器：

```nginx
location = /api/v1/events {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    gzip off;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";
}
```

`proxy_pass` 改成实际的上游即可。改完后重载 Nginx，不需要单独的发布步骤；应用侧的表由 `python -m app.prepare` 里的 Alembic 迁移 `0021_domain_events` 创建。

本地没有这层反代时（Vite 把 `/api` 转到 8000，或浏览器直连 API），不需要改 Nginx。

## 没有改成 SSE 的定时器

- `EventPhaseStatus` 的 1 秒间隔只推进本地倒计时。
- 下载完成检测轮询的是浏览器 Cookie，不是服务端领域状态。

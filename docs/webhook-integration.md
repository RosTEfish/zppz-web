# ZPPZ 谱面 Webhook 接入手册

网站通过 HTTPS Webhook 向外部 Bot 推送谱面首次发布和更新事件。接入方无需轮询网站，但必须提供公网 HTTPS（443）回调地址，并按 `event_id` 去重。

## 1. 凭据

向网站 Owner 获取以下两项一次性凭据：

```text
integration_token = zppz_whk_...
webhook_secret = ...
```

Token 用于调用订阅管理 API，Secret 用于校验网站发送的 Webhook。凭据轮换后旧值立即失效。

## 2. 注册回调

先启动 Bot 的 HTTPS 接收接口，再注册：

```http
PUT https://przppz.club/api/v1/integrations/webhook-subscription
Authorization: Bearer <integration_token>
Content-Type: application/json

{
  "callback_url": "https://bot.example.com/webhooks/zppz",
  "events": ["chart.published", "chart.updated"],
  "schema_version": 1
}
```

网站会立即向 `callback_url` 发送 `webhook.verification`。接收方校验签名后必须返回：

```json
{"challenge":"请求中的 challenge 原值"}
```

验证成功后注册 API 返回 `active`。相同配置可安全重复 `PUT`。

可用管理接口：

```http
GET    /api/v1/integrations/webhook-subscription
DELETE /api/v1/integrations/webhook-subscription
POST   /api/v1/integrations/webhook-subscription/test
```

新订阅只接收首次激活后的事件，不补发历史谱面。

## 3. 签名校验

每次请求包含：

```http
X-ZPPZ-Event-ID: <event_id>
X-ZPPZ-Timestamp: <Unix 秒>
X-ZPPZ-Signature: sha256=<hex>
```

签名原文必须使用收到的原始请求体字节，不能先解析再重新序列化：

```text
HMAC-SHA256(webhook_secret, timestamp + "." + raw_body)
```

接收方应使用常量时间比较签名，并拒绝与当前时间相差超过五分钟的请求。

Python 验证示例：

```python
import hashlib
import hmac
import time

timestamp = request.headers["X-ZPPZ-Timestamp"]
provided = request.headers["X-ZPPZ-Signature"].removeprefix("sha256=")
if abs(int(time.time()) - int(timestamp)) > 300:
    raise ValueError("stale webhook")
expected = hmac.new(
    WEBHOOK_SECRET.encode(),
    timestamp.encode() + b"." + raw_request_body,
    hashlib.sha256,
).hexdigest()
if not hmac.compare_digest(expected, provided):
    raise ValueError("invalid signature")
```

## 4. 谱面事件

```json
{
  "schema_version": 1,
  "event_id": "5e5428ab3f8d4bf297b96624288dbf25",
  "event_type": "chart.published",
  "occurred_at": "2026-08-02T12:30:00Z",
  "competition": {
    "id": 5,
    "slug": "zppz-current",
    "name": "这谱谱这无名战 #5"
  },
  "source": {
    "type": "normal",
    "id": 42,
    "revision": 1
  },
  "chart_set": {
    "title": "Example Song",
    "artist": "Example Artist",
    "track": "normal",
    "is_self_selected": true,
    "levels": [
      {"chart_id": 301, "slot": "4", "level": "13+", "designer": "某谱师"}
    ],
    "cover": {
      "url": "https://przppz.club/api/v1/integrations/webhook-assets/...",
      "content_type": "image/png",
      "width": 512,
      "height": 512,
      "size_bytes": 184321,
      "sha256": "...",
      "expires_at": "2026-08-09T12:30:00Z"
    },
    "page_url": "https://przppz.club/guess"
  },
  "changes": null
}
```

事件类型：

- `chart.published`：一份谱面来源首次公开。
- `chart.updated`：已公开来源的投稿文件或公开元数据发生更新。
- `webhook.test`：手动测试，不代表真实谱面。
- `webhook.verification`：注册验证，不进入正常消息队列。

一次投稿包含多个难度时，所有难度位于同一个 `levels` 数组。`chart.updated` 的 `changes` 包含 `changed_fields`、`levels_added`、`levels_removed` 和 `levels_changed`。

`cover` 可能为 `null`，仅发生在源谱面确实没有有效封面时。封面 URL 有效期为七天；Bot 应在收到事件后及时下载，并可使用 `sha256` 校验内容。封面 URL 可能返回 `307` 到对象存储，下载客户端应允许资产请求跟随重定向。

## 5. 响应、去重和重试

- 返回任意 `2xx` 表示事件已持久接收。
- 网站不会跟随 Webhook 回调返回的重定向。
- 非 `2xx`、超时或网络错误会重试最多七天。
- 同一事件可能被发送多次；必须以 `event_id` 建立唯一约束并幂等处理。
- 建议先把事件写入 Bot 自己的 inbox/数据库，再返回 `2xx`，随后异步发送 QQ 群消息。
- 同一接收方按事件顺序投递；较早事件未成功时，后续事件会等待。

不要把 Integration Token、Webhook Secret 或带签名的封面 URL写入公开日志。

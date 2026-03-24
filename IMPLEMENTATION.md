# Web3 Monitor 实现文档

**当前版本**: v1.0.0
**更新日期**: 2026-03-24

## 一、项目简介

Web3 Monitor 是一个 Twitter/X KOL 实时监控系统，核心功能是自动追踪指定 Twitter 账号的新推文，翻译成中文后通过飞书推送通知，并在紧急情况下通过飞书电话加急功能拨打电话叫醒用户。

## 二、整体架构

```
[Twitter API]  →  [Python 监控服务]  →  [飞书通知]
(twitter241)      (FastAPI + 轮询线程)    (Webhook + 电话加急)
                        ↕
                   [SQLite 数据库]
                        ↕
               [前端网站 (Vercel)]
               落地页/仪表盘/定价/登录
```

- **后端**: Python FastAPI，本地或 VPS 运行，提供监控轮询 + REST API
- **前端**: 纯 HTML/CSS/JS，部署到 Vercel
- **存储**: SQLite 单文件数据库
- **通信**: 前端通过 HTTP 调用后端 API（CORS 跨域）

## 三、核心文件与职责

| 文件 | 职责 |
|------|------|
| `monitor/main.py` | 主入口，FastAPI 服务 + 后台轮询线程 + 全部 REST API 端点 |
| `monitor/twitter_poller.py` | Twitter API 封装：用户搜索、推文获取、增量轮询 |
| `monitor/feishu_notifier.py` | 飞书通知全流程：Webhook 卡片推送 + 获取 token + 电话加急 + 已读检测 + 智能重试 |
| `monitor/translator.py` | 推文翻译（英文 → 中文），保留 @mention 和链接 |
| `monitor/db.py` | SQLite 数据层，5 张表的建表和 CRUD 操作 |
| `monitor/config.py` | 从 .env 文件加载所有配置项 |
| `public/index.html` | 落地页：Hero 区 + 功能介绍 + 工作流程 + CTA |
| `public/dashboard.html` | 仪表盘：概览统计 + 监控管理 + 推文历史 + 通知设置 |
| `public/pricing.html` | 定价页：Free/Pro/Enterprise 三档 + 支付弹窗 |
| `public/login.html` | 登录/注册页 |

## 四、监控轮询逻辑

监控服务启动后，后台线程每 **5 分钟** 执行一次轮询循环：

```
1. 从数据库读取所有 is_active=True 的监控账号

2. 对每个账号:
   a. 调用 twitter241 API /user-tweets 接口获取最新 20 条推文
   b. 用 last_tweet_id 过滤，只保留该 ID 之后的新推文
   c. 对每条新推文:
      - 调用 deep-translator 将英文翻译成中文
      - 存入 tweets 表（按 tweet_id 去重）
      - 发送飞书 Webhook 卡片通知（包含原文 + 翻译 + 互动数据）
      - 如果账号 priority = urgent → 启动新线程触发电话加急
   d. 更新该账号的 last_tweet_id 为最新推文 ID

3. 休眠 300 秒（可配置），回到步骤 1
```

**关键设计**:
- 增量轮询：通过 last_tweet_id 避免重复处理
- 异常隔离：单个账号失败不影响其他账号
- tweet_id 唯一约束：数据库层面防止重复入库

## 五、飞书电话加急流程

当 urgent 优先级的账号有新推文时，系统在独立线程中执行：

```
步骤 1: 获取 tenant_access_token
  POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal
  Body: { app_id, app_secret }
  → 返回 token（有效期 2 小时，带缓存）

步骤 2: 给用户发送消息
  POST https://open.feishu.cn/open-apis/im/v1/messages
  Headers: Authorization: Bearer {token}
  Body: { receive_id: 用户open_id, msg_type: text, content: 推文内容 }
  → 返回 message_id

步骤 3: 触发电话加急
  PATCH https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/urgent_phone
  Body: { user_id_list: [用户open_id] }
  → 飞书拨打电话给用户

步骤 4: 智能重试循环
  等待 120 秒（可配置）
  GET https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/read_users
  → 检查用户是否已读消息
    - 已读 → 停止，用户已被唤醒
    - 未读 → 回到步骤 3 重新拨打
    - 最多重试 3 次（可配置）后停止
```

## 六、飞书 Webhook 通知格式

使用飞书 interactive 卡片消息，包含：

```json
{
  "msg_type": "interactive",
  "card": {
    "header": { "title": "[推文] @sama (Sam Altman)", "template": "blue" },
    "elements": [
      { "tag": "markdown", "content": "**原文:** ..." },
      { "tag": "markdown", "content": "**翻译:** ..." },
      { "tag": "markdown", "content": "点赞 X | 转推 X | 回复 X | 时间" }
    ]
  }
}
```

## 七、Twitter API 调用方式

使用 RapidAPI 的 twitter241 服务：

**搜索用户** (`/user`):
```
GET https://twitter241.p.rapidapi.com/user?username=sama
返回结构: result.data.user.result
  - rest_id: 用户 ID
  - core.screen_name: 用户名
  - core.name: 显示名
  - avatar.image_url: 头像
```

**获取推文** (`/user-tweets`):
```
GET https://twitter241.p.rapidapi.com/user-tweets?user={user_id}&count=20
返回结构: result.timeline.instructions[].entries[]
  每条 entry 中: content.itemContent.tweet_results.result.legacy
    - id_str: 推文 ID
    - full_text: 推文全文
    - created_at: 发布时间
    - favorite_count/retweet_count/reply_count: 互动数据
```

## 八、数据库设计（SQLite 5 张表）

**users** - 用户表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| username | TEXT UNIQUE | 用户名 |
| email | TEXT UNIQUE | 邮箱 |
| password_hash | TEXT | bcrypt 哈希 |
| plan | TEXT | 套餐: free/pro/enterprise |
| created_at | TIMESTAMP | 创建时间 |

**monitors** - 监控账号表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| user_id | INTEGER FK | 关联用户 |
| twitter_username | TEXT | Twitter 用户名 |
| twitter_user_id | TEXT | Twitter 用户 ID |
| display_name | TEXT | 显示名称 |
| is_active | BOOLEAN | 是否启用 |
| priority | TEXT | normal/important/urgent |
| last_tweet_id | TEXT | 最后处理的推文 ID |

**tweets** - 推文记录表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| tweet_id | TEXT UNIQUE | 推文 ID（去重键） |
| monitor_id | INTEGER FK | 关联监控账号 |
| content_original | TEXT | 原文 |
| content_translated | TEXT | 中文翻译 |
| tweet_type | TEXT | tweet/retweet/reply/quote |
| metrics | TEXT | 互动数据 JSON |

**notifications** - 通知记录表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| tweet_id | INTEGER FK | 关联推文 |
| channel | TEXT | webhook/phone/email |
| status | TEXT | sent/delivered/read/failed |
| message_id | TEXT | 飞书消息 ID |
| retry_count | INTEGER | 重试次数 |

**settings** - 用户设置表
| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | INTEGER FK | 关联用户 |
| feishu_webhook_url | TEXT | 飞书 Webhook |
| feishu_user_id | TEXT | 飞书 Open ID |
| phone_enabled | BOOLEAN | 是否启用电话 |
| phone_retry_max | INTEGER | 最大重试次数 |
| poll_interval | INTEGER | 轮询间隔（秒） |

## 九、API 端点

| 方法 | 端点 | 功能 |
|------|------|------|
| POST | /api/auth/register | 注册，返回 JWT |
| POST | /api/auth/login | 登录，返回 JWT |
| GET | /api/auth/me | 获取当前用户信息 |
| GET | /api/monitors | 获取监控账号列表 |
| POST | /api/monitors | 添加监控（自动搜索 Twitter 用户） |
| PUT | /api/monitors/{id} | 更新优先级/启停 |
| DELETE | /api/monitors/{id} | 删除监控 |
| GET | /api/tweets | 分页查询推文历史 |
| GET | /api/tweets/stats | 统计概览 |
| GET | /api/settings | 获取通知设置 |
| PUT | /api/settings | 更新通知设置 |
| GET | /api/health | 健康检查 |

## 十、前端页面

| 页面 | 路径 | 内容 |
|------|------|------|
| 落地页 | `/` | Hero + 6 功能卡片 + 3 步骤流程 + CTA |
| 登录页 | `/login.html` | 登录/注册双 Tab |
| 仪表盘 | `/dashboard.html` | 概览统计、监控管理、推文历史、通知设置 4 个面板 |
| 定价页 | `/pricing.html` | Free/Pro/Enterprise + 支付弹窗（信用卡/微信/支付宝 UI） |

设计风格：深色科技风主题，蓝色渐变强调色。

## 十一、技术选型

| 组件 | 技术 | 理由 |
|------|------|------|
| 后端框架 | FastAPI | 异步支持、自带 Swagger 文档、轻量 |
| 数据库 | SQLite | 零配置、单文件、适合个人产品 |
| Twitter 数据 | twitter241 (RapidAPI) | 免费额度、无需官方开发者账号 |
| 翻译 | deep-translator (Google) | 免费、质量够用 |
| 认证 | JWT + bcrypt | 标准方案、密码安全 |
| 前端 | 纯 HTML/CSS/JS | 无构建步骤、直接静态部署 |
| 前端托管 | Vercel | 免费、自动 CDN、支持自定义域名 |

## 十二、环境变量配置

| 变量 | 说明 | 必填 |
|------|------|------|
| RAPIDAPI_KEY | RapidAPI 密钥 | 是 |
| RAPIDAPI_HOST | API 主机名 | 否，默认 twitter241.p.rapidapi.com |
| FEISHU_WEBHOOK_URL | 飞书群机器人 Webhook | 是 |
| FEISHU_APP_ID | 飞书自建应用 App ID | 电话加急需要 |
| FEISHU_APP_SECRET | 飞书自建应用 App Secret | 电话加急需要 |
| FEISHU_USER_ID | 接收电话的用户 Open ID | 电话加急需要 |
| POLL_INTERVAL | 轮询间隔秒数 | 否，默认 300 |
| PHONE_RETRY_MAX | 电话最大重试次数 | 否，默认 3 |
| PHONE_RETRY_INTERVAL | 重试间隔秒数 | 否，默认 120 |
| JWT_SECRET | JWT 签名密钥 | 是 |
| API_PORT | API 服务端口 | 否，默认 8080 |

## 十三、部署方式

**启动后端服务:**
```powershell
cd E:\Project\AX\web3-monitor
pip install -r requirements.txt
python -m monitor.main
```

**部署前端到 Vercel:**
```powershell
vercel deploy --prod
```

**线上地址:** https://web3-monitor-zeta.vercel.app

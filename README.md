# Web3 Monitor

Twitter KOL 实时监控系统 -- 自动追踪推文、翻译推送、飞书电话叫醒。

## 功能特性

- **实时监控** - 每 5 分钟自动轮询目标 Twitter 账号的新推文
- **自动翻译** - 英文推文自动翻译为中文
- **飞书推送** - 通过 Webhook 发送卡片消息到飞书群（原文 + 翻译 + 互动数据）
- **电话加急** - urgent 优先级账号触发飞书电话提醒，未读自动重拨
- **多账号管理** - 支持同时监控多个 Twitter 账号，独立设置优先级
- **Web 仪表盘** - 完整的前端界面：监控管理、推文历史、通知设置

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | Python + FastAPI |
| 数据库 | SQLite |
| Twitter 数据 | twitter241 (RapidAPI) |
| 翻译 | deep-translator (Google Translate) |
| 通知 | 飞书 Webhook + 飞书电话加急 API |
| 前端 | HTML / CSS / JS |
| 部署 | Vercel (前端) + 本地/VPS (后端) |

## 快速开始

### 1. 安装依赖

```bash
cd web3-monitor
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，填入你的配置：

```bash
cp .env.example .env
```

需要准备：
- **RapidAPI Key** - 在 [RapidAPI](https://rapidapi.com/davethebeast/api/twitter241) 订阅 twitter241
- **飞书 Webhook** - 在飞书群中添加自定义机器人，获取 Webhook URL
- **飞书自建应用** - 在 [飞书开放平台](https://open.feishu.cn) 创建应用，获取 App ID 和 App Secret（电话加急需要）
- **飞书 Open ID** - 通过飞书 API 获取你的 open_id（电话加急需要）

### 3. 启动服务

```bash
python -m monitor.main
```

服务启动后：
- API 在 `http://localhost:8080` 提供服务
- 后台线程自动轮询监控账号
- 访问 `http://localhost:8080/api/health` 检查服务状态

### 4. 使用

1. 注册账号并登录
2. 在 Dashboard 中添加要监控的 Twitter 账号
3. 设置优先级（normal / important / urgent）
4. 配置飞书通知参数
5. 系统自动运行，新推文会推送到飞书

## 项目结构

```
web3-monitor/
├── monitor/                # Python 后端
│   ├── main.py             # 主入口：FastAPI + 轮询线程
│   ├── twitter_poller.py   # Twitter API 轮询
│   ├── feishu_notifier.py  # 飞书通知（Webhook + 电话）
│   ├── translator.py       # 翻译模块
│   ├── db.py               # SQLite 数据层
│   └── config.py           # 配置加载
├── public/                 # 前端静态文件
│   ├── index.html          # 落地页
│   ├── dashboard.html      # 仪表盘
│   ├── pricing.html        # 定价页
│   └── login.html          # 登录页
├── IMPLEMENTATION.md       # 详细实现文档
├── .env.example            # 环境变量模板
├── requirements.txt        # Python 依赖
└── vercel.json             # Vercel 部署配置
```

## 线上地址

https://web3-monitor-zeta.vercel.app

## 详细文档

完整的实现逻辑、API 接口、数据库设计见 [IMPLEMENTATION.md](./IMPLEMENTATION.md)

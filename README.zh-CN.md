# Slack Codex Bridge

[English](./README.md) | [简体中文](./README.zh-CN.md)

从 Slack 控制本机运行的 `codex` CLI。

这个仓库运行一个本地守护进程，通过 Slack Socket Mode 接收消息，把 Slack 线程映射到本机 Codex session，并把最终结果回发到 Slack。它支持按线程切换工作目录、高风险操作审批，以及根据 Codex 回复中的图片标记上传本地图片。

## 核心能力

- 通信链路：`Slack Socket Mode -> 本地守护进程 -> codex exec/resume`
- 权限边界：只有配置在白名单里的 Slack 用户可以发起请求
- 会话模型：
  - 在 DM 里，每条顶层消息都会创建一个新的 Codex session
  - 在 DM 里，只有对同一条消息 `Reply in thread` 才会复用该 session
  - 在频道里，每个 Slack thread 对应一个 Codex session
- 工作目录模型：
  - 每个 Slack thread 都可以绑定自己的本地 `workspace_root`
  - 切换工作目录会清空该线程当前绑定的 Codex session
- 风险模型：
  - 低风险请求直接执行
  - 高风险请求先在 Slack 中确认，再真正执行
- 输出模型：
  - Codex 执行完成后统一回发最终文本
  - 如果 Codex 回复里包含图片标记，bridge 会把对应本地图片上传到同一个 Slack 线程

## 面向 Agent 的协议

每次创建新的 Codex session 时，bridge 都会自动在第一条 prompt 前追加一段说明，告诉 Codex 如何请求上传本地图片。

Codex 只要在最终回复中包含下面这种标记，bridge 就会尝试上传图片：

```text
[[image:/absolute/path/to/file.png]]
```

规则：

- 必须使用绝对路径
- 支持多张图，每行一个标记
- 支持的后缀：`.png`、`.jpg`、`.jpeg`、`.gif`、`.webp`
- 图片必须位于当前工作目录或 `/tmp` 下

bridge 会先把图片标记从文本中去掉，再把纯文本回复发到 Slack。

## Slack 命令

- `/status`
  - 显示当前线程绑定的工作目录和 Codex session
- `/new`
  - 清空当前线程的 Codex session；下一条普通消息会创建新的 session
- `/reset`
  - 删除当前线程的会话映射
- `/stop`
  - `/reset` 的别名
- `/workspace /absolute/path/to/repo`
  - 把当前 Slack 线程绑定到新的本地工作目录
  - 同时清空当前线程的 Codex session

## 配置与启动

### 1. 配置 Slack App

在 `https://api.slack.com/apps` 创建应用。

#### 创建 Slack App

- 点击 `Create New App`
- 选择 `From scratch`
- 选择目标 workspace

#### 启用 Socket Mode

- 打开 `Socket Mode`
- 开启 `Enable Socket Mode`
- 生成一个带 `connections:write` 的 app-level token
- 把它保存为 `SLACK_APP_TOKEN`

#### 配置 App Home

- 打开 `App Home`
- 开启 `Messages Tab`
- 开启 `Allow users to send Slash commands and messages from the messages tab`

#### 配置 Event Subscriptions

- 打开 `Event Subscriptions`
- 开启 events
- 在 `Subscribe to bot events` 中添加：
  - `message.im`
  - `app_mention`

#### 添加 Bot Token Scopes

- 打开 `OAuth & Permissions`
- 在 `Bot Token Scopes` 中添加：
  - `app_mentions:read`
  - `channels:history`
  - `chat:write`
  - `files:write`
  - `groups:history`
  - `im:history`
  - `im:write`
  - `mpim:history`

#### 安装或重新安装到 Workspace

- 在 `OAuth & Permissions` 页面点击 `Install to Workspace` 或 `Reinstall to Workspace`
- 把得到的 bot token 保存为 `SLACK_BOT_TOKEN`

#### 找到你的 Slack 用户 ID

- 打开你的 Slack 个人资料
- 找到成员 ID，例如 `U01234567`
- 把它填到 `ALLOWED_SLACK_USER_IDS`

#### 填写 `.env`

你至少需要以下配置：

- `SLACK_BOT_TOKEN`
- `SLACK_APP_TOKEN`
- `SLACK_SIGNING_SECRET`
- `ALLOWED_SLACK_USER_IDS`

`SLACK_SIGNING_SECRET` 可以在 `Basic Information -> App Credentials` 中找到。

### 2. 本地安装

推荐用 conda：

```bash
conda env create -f environment.yml
conda activate slack-codex-bridge
```

也可以用原生 Python：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 3. 配置环境变量

把 `.env.example` 复制为 `.env`，然后填写配置。

重要变量：

- `ALLOWED_SLACK_USER_IDS`
  - 允许控制 bridge 的 Slack 用户 ID，逗号分隔
- `WORKSPACE_ROOT`
  - 新 session 的默认工作目录
- `CODEX_BIN`
  - 本机 `codex` 可执行文件路径
- `CODEX_EXTRA_ARGS`
  - 传给 `codex exec` 的额外参数

### 4. 启动守护进程

```bash
python -m slack_codex_bridge.app
```

bridge 会使用 `.runtime/bridge.lock` 做单实例保护，因此同一时间只能运行一个实例。

## 使用方式

### 启动一个新的 DM 任务

直接给 bot 发一条顶层私信：

```text
Explain what this repository does.
```

这会创建一个新的 Codex session。

### 继续同一个任务

对那条消息点击 `Reply in thread`，并在这个 thread 里继续对话。

### 切换当前线程的工作目录

```text
/workspace /home/user/code/another_repo
```

下一条普通消息会在新的工作目录下启动一个新的 Codex session。

### 请求返回图片

你可以直接让 Codex 生成本地图片并通过 bridge 发回 Slack，例如：

```text
Draw a diagram, save it as a PNG in the current repo, and return it to Slack.
```

只要 Codex 输出了合法的图片标记，且文件路径符合规则，bridge 就会自动上传。

## 运行时状态

运行时数据存放在 `.runtime/` 目录下。

重要文件：

- `.runtime/audit.log`
  - JSONL 格式的审计日志，记录收消息、审批、Codex 执行、图片上传等事件
- `.runtime/sessions.json`
  - Slack thread 到 Codex session 的映射，以及每线程的工作目录状态
- `.runtime/bridge.lock`
  - 单实例锁文件

## 仓库结构

- [src/slack_codex_bridge/app.py](/home/sunpq/codes/slack_codex/src/slack_codex_bridge/app.py)
  - Slack 事件处理、命令解析、审批逻辑、结果回传
- [src/slack_codex_bridge/codex_client.py](/home/sunpq/codes/slack_codex/src/slack_codex_bridge/codex_client.py)
  - 本地 `codex exec/resume` 封装
- [src/slack_codex_bridge/session_store.py](/home/sunpq/codes/slack_codex/src/slack_codex_bridge/session_store.py)
  - 持久化保存 thread/session/workspace 映射
- [src/slack_codex_bridge/attachments.py](/home/sunpq/codes/slack_codex/src/slack_codex_bridge/attachments.py)
  - 图片标记解析与上传路径校验

## 限制

- 不支持 token 级流式回传，只会在 Codex 完成后统一回复
- 风险分类目前是启发式规则，不是强语义理解
- 待确认的审批状态只保存在内存中
- 图片上传依赖 Codex 正确输出图片标记
- 已存在的旧 session 不会自动继承新的 bootstrap 指令；如有需要，请使用 `/new` 或 `/reset`

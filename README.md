# Slack Codex Bridge

[English](./README.md) | [简体中文](./README.zh-CN.md)

Control a local `codex` CLI agent from Slack.

This repository runs a local daemon that connects to Slack over Socket Mode, accepts messages from an allowlisted user, maps Slack threads to Codex sessions, and sends final results back to Slack. It also supports per-thread workspace switching, approval for high-risk requests, and uploading local image files mentioned by Codex replies.

## Core behavior

- Transport: `Slack Socket Mode -> local daemon -> codex exec/resume`
- Trust boundary: only configured Slack user IDs may issue requests
- Session model:
  - In DM, each top-level Slack message starts a new Codex session
  - In DM, replies in the same Slack thread reuse that session
  - In channels, each Slack thread maps to one Codex session
- Workspace model:
  - Each Slack thread can bind to its own local `workspace_root`
  - Changing workspace clears the current Codex session for that thread
- Risk model:
  - Low-risk prompts execute immediately
  - High-risk prompts require Slack button confirmation before execution
- Output model:
  - The bridge posts the final text reply after Codex completes
  - If Codex includes image markers, the bridge uploads those local images to the same Slack thread

## Agent-facing protocol

When a new Codex session is created, the bridge prepends an instruction that tells Codex how to request image uploads.

Codex can ask the bridge to upload a local image by including this exact marker in its final reply:

```text
[[image:/absolute/path/to/file.png]]
```

Rules:

- Use absolute paths only
- Multiple images are allowed, one marker per line
- Supported suffixes: `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`
- Uploaded files must be under the active workspace or `/tmp`

The bridge strips image markers from the text reply before posting text to Slack.

## Slack commands

- `/status`
  - Show the current workspace and mapped Codex session for the current Slack thread
- `/new`
  - Clear the current Codex session for the thread; the next normal message starts a new session
- `/reset`
  - Remove the thread mapping
- `/stop`
  - Alias of `/reset`
- `/workspace /absolute/path/to/repo`
  - Bind the current Slack thread to a different local workspace
  - Clears the current Codex session for that thread

## Setup

### 1. Configure the Slack app

Create the app at `https://api.slack.com/apps`.

#### Create the Slack app

- Click `Create New App`
- Choose `From scratch`
- Pick the target workspace

#### Enable Socket Mode

- Open `Socket Mode`
- Turn on `Enable Socket Mode`
- Generate an app-level token with `connections:write`
- Save it as `SLACK_APP_TOKEN`

#### Configure App Home

- Open `App Home`
- Enable `Messages Tab`
- Enable `Allow users to send Slash commands and messages from the messages tab`

#### Configure Event Subscriptions

- Open `Event Subscriptions`
- Enable events
- Under `Subscribe to bot events`, add:
  - `message.im`
  - `app_mention`

#### Add Bot Token Scopes

- Open `OAuth & Permissions`
- Under `Bot Token Scopes`, add:
  - `app_mentions:read`
  - `channels:history`
  - `chat:write`
  - `files:write`
  - `groups:history`
  - `im:history`
  - `im:write`
  - `mpim:history`

#### Install or reinstall to workspace

- In `OAuth & Permissions`, click `Install to Workspace` or `Reinstall to Workspace`
- Save the bot token as `SLACK_BOT_TOKEN`

#### Find your Slack user ID

- Open your Slack profile
- Copy your member ID, e.g. `U01234567`
- Put it into `ALLOWED_SLACK_USER_IDS`

#### Fill `.env`

You will need:

- `SLACK_BOT_TOKEN`
- `SLACK_APP_TOKEN`
- `SLACK_SIGNING_SECRET`
- `ALLOWED_SLACK_USER_IDS`

The signing secret is available in `Basic Information -> App Credentials`.

### 2. Install locally

```bash
conda env create -f environment.yml
conda activate slack-codex-bridge
```

Or with plain Python:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 3. Configure environment

Copy `.env.example` to `.env` and fill in values.

Important variables:

- `ALLOWED_SLACK_USER_IDS`
  - Comma-separated Slack user IDs allowed to control the daemon
- `WORKSPACE_ROOT`
  - Default workspace for new sessions
- `CODEX_BIN`
  - Path to the local `codex` executable
- `CODEX_EXTRA_ARGS`
  - Extra flags passed to `codex exec`

### 4. Start the daemon

```bash
python -m slack_codex_bridge.app
```

The daemon uses a lock file under `.runtime/bridge.lock`, so only one instance can run at a time.

## How to use

### Start a fresh DM task

Send a top-level DM message to the bot:

```text
Explain what this repository does.
```

That creates a new Codex session.

### Continue the same task

Use `Reply in thread` on that message and continue inside that Slack thread.

### Switch workspace for one thread

```text
/workspace /home/user/code/another_repo
```

The next normal message in that thread starts a new Codex session in the new workspace.

### Ask for an image reply

You can explicitly ask Codex to produce a local image and return it via the bridge:

```text
Draw a diagram, save it as a PNG in the current repo, and return it to Slack.
```

If Codex emits a valid image marker and the file exists in an allowed path, the bridge uploads it.

## Runtime state

The bridge stores local runtime state under `.runtime/`.

Important files:

- `.runtime/audit.log`
  - JSONL audit events for message receipt, approvals, Codex runs, and image uploads
- `.runtime/sessions.json`
  - Thread-to-session mapping and per-thread workspace state
- `.runtime/bridge.lock`
  - Single-instance lock file

## Repository layout

- [src/slack_codex_bridge/app.py](/home/sunpq/codes/slack_codex/src/slack_codex_bridge/app.py)
  - Slack event handling, command parsing, approvals, and reply flow
- [src/slack_codex_bridge/codex_client.py](/home/sunpq/codes/slack_codex/src/slack_codex_bridge/codex_client.py)
  - Local `codex exec/resume` wrapper
- [src/slack_codex_bridge/session_store.py](/home/sunpq/codes/slack_codex/src/slack_codex_bridge/session_store.py)
  - Persistent thread/session/workspace mapping
- [src/slack_codex_bridge/attachments.py](/home/sunpq/codes/slack_codex/src/slack_codex_bridge/attachments.py)
  - Image marker parsing and upload path validation

## Limits

- No streaming token-by-token Slack updates; replies are sent after Codex completes
- Risk classification is heuristic
- Pending approvals are in memory only
- Image upload depends on Codex emitting valid markers
- Existing old sessions do not automatically inherit new bootstrap instructions; use `/new` or `/reset` when needed

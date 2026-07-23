# ClaxCode

> 开源、自托管的终端 AI 编程助手 —— 类 Claude Code 的 Agentic 体验，接入任意 LLM，数据不出本机。

**English**: ClaxCode is an open-source, self-hosted agentic coding assistant inspired by Claude Code. It runs in your terminal (plus a FastAPI/SSE server), works with any LLM (OpenAI, Anthropic, Ollama, any OpenAI-compatible or custom HTTP API), and keeps all data on your machine. Features an agentic loop, 35 built-in tools, layered permission modes with interactive approval, file snapshots with rollback, shell hooks, a six-layer skill system, persistent memory, subagents, and a headless mode for scripting.

## 为什么选择 ClaxCode

- 🔌 **任意模型** — OpenAI / Anthropic / Ollama / vLLM / DashScope / 自定义 HTTP 模板，甚至代码注册自己的 Provider
- 🧠 **真 Agentic Loop** — 收集上下文 → 思考（流式）→ 调用工具 → 验证，最多 10 轮自主迭代
- 🛡️ **安全分层** — 5 级权限模式 + 逐项审批 + 编辑前快照 + 一键回滚 + 全程审计日志
- 🧩 **高度可扩展** — Skills 六层加载、Shell Hooks、子代理、35 个内置工具
- 💾 **有记忆** — 会话断点续聊、LLM 摘要压缩、长期记忆、自动记忆偏好
- 🖥️ **双前端** — 交互式 CLI（REPL）+ FastAPI SSE 流式服务
- ✅ **110 个自动化测试**，ruff/mypy 受控

## 快速开始

```bash
# 安装（Python >= 3.11）
git clone <repo-url> && cd ClaxCode
python -m venv .venv && .\.venv\Scripts\activate   # Windows
pip install -e ".[dev]"

# 配置
cp .env.example .env   # 填入你的 LLM_API_KEY 等

# 启动交互式终端
claxcode-cli

# 单发模式（可脚本化）
claxcode-cli --print "总结一下这个项目的结构"
```

最小配置（`.env`）：

```env
LLM_PROVIDER=generic_openai      # openai | anthropic | generic_openai | ollama | custom_http
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://your-endpoint/v1
LLM_MODEL=your-model
```

## 三分钟上手

```text
❯ 帮我重构 @claxcode/core/context.py，加上类型 hint        # @文件 内联文件内容
❯ !git status                                               # ! 直接执行 shell
❯ #用户偏好简洁的回答                                        # # 存入自动记忆
❯ /mode auto_safe                                           # 切换权限模式
❯ /rollback list                                            # 查看可回滚的编辑快照
```

Agent 工作时的样子：

```text
💭 思考中... (步骤 1)
🔧 调用工具: read_file({"path": "claxcode/core/context.py"})
📋 结果: ...
💭 正在验证结果...
已为你完成重构：1) 补齐类型标注 2) ...
```

## 权限模式

| 模式 | 行为 |
|---|---|
| `ask`（默认） | 只读工具自动放行；写/执行逐项询问（`y` 允许 / `a` 本会话放行该工具 / `N` 拒绝） |
| `plan` | 只读模式，阻断一切写/执行工具 |
| `auto_safe` | 放行读和写，阻断命令执行 |
| `auto_edit` | 全部放行 |
| `yolo` | 全部放行（完全自动驾驶，慎用） |

```bash
claxcode-cli --mode plan        # 只读探索，绝不改文件
claxcode-cli --mode auto_safe   # 可改代码，不跑命令
```

安全机制：**每次写操作前自动快照**（`.claxcode/snapshots/`），`/rollback` 可回滚；所有工具调用（含被阻止的）写入 `.claxcode/audit.jsonl` 审计日志，`/audit` 随时查看。

## 斜杠命令

`/help` 由命令表自动生成，永不过时：

| 命令 | 说明 |
|---|---|
| `/help` | 显示帮助（含技能命令） |
| `/tools` | 列出 35 个可用工具 |
| `/mode <mode>` | 切换权限模式（支持方向键选择） |
| `/skills [reload\|create]` | 技能列表 / 热重载 / 新建技能 |
| `/project [list\|switch\|info]` | 项目管理 |
| `/memory [list\|search\|learn\|forget\|facts\|export\|import\|delete]` | 记忆管理 |
| `/compact` | 压缩当前会话并存入长期记忆 |
| `/rollback [n\|list]` | 回滚最近 n 个编辑快照 |
| `/audit [n]` | 查看最近 n 条审计日志 |
| `/init` | 初始化项目信息（生成 CLAUDE.md） |
| `/config` `/debug` `/clear` | 配置 / 调试 / 清空上下文 |
| `/exit` `/quit` | 退出 |

输入前缀：`!cmd` 直接跑 shell · `@path` 内联文件内容 · `#text` 快速记忆。Skills 在 `## Commands` 中定义的命令（如 `/refactor_file`）可直接调用。

## Skills — 可复用的能力包

一个技能 = 一个含 `SKILL.md` 的目录（+ 可选 `tools.py` 注册专属工具），内容自动注入系统提示词。六层加载，同名后者覆盖前者：

| 级别 | 路径 |
|---|---|
| 内置（随包发布） | `claxcode/skills/`（自带 `python-refactor`） |
| 用户级 | `~/.claxcode/skills/`、`~/.agent/skills/` |
| 项目级 | `./.claxcode/skills/`、`./.agent/skills/`、`./skills/` |

```bash
/skills create my-skill    # 生成规范的技能脚手架
/skills reload             # 改完热重载，无需重启
```

## Hooks — 工具调用的生命周期钩子

在 `~/.claxcode/hooks.json`（全局）或 `<项目>/.claxcode/hooks.json`（项目）中配置 shell 钩子：

```json
{
  "PreToolUse": [
    {"match": "run_shell", "command": "python scripts/guard.py"},
    {"match": "write_file|edit_file", "command": "python scripts/check_branch.py"}
  ],
  "PostToolUse": [
    {"match": "write_file", "command": "python scripts/lint_changed.py"}
  ]
}
```

- `match` 是匹配工具名的正则（空或 `*` 匹配全部）
- 钩子从 stdin 收到 JSON（工具名/参数/结果），环境变量 `CLAXCODE_TOOL_NAME`、`CLAXCODE_TOOL_ARGS`（Windows 用 `%VAR%`，bash 用 `$VAR`）
- **PreToolUse 退出码非 0 → 阻断该工具调用**；钩子超时/启动失败不会阻塞主流程

## 记忆系统

| 层 | 存储 | 说明 |
|---|---|---|
| 会话消息 | SQLite（`sessions` 表） | 每轮自动保存；API 按会话恢复，CLI 启动自动续聊（`/clear` 重开） |
| 自动记忆 | `~/.claxcode/auto_memory.json` | 用户偏好/事实，注入系统提示；`#` 快捷记录、agent 也可用 `remember_fact` 工具自记 |
| 长期记忆 | SQLite | `/compact` 用 LLM 压缩会话存档，按关键词检索，新会话自动注入相关记忆 |
| 项目记忆 | SQLite + `CLAUDE.md` | `/init` 采集项目信息，每次会话自动加载 |

上下文超长时自动触发 LLM 摘要压缩（保留系统提示，早期对话浓缩为摘要）。

## 工具一览（35 个）

文件操作 ×7 · 搜索 ×3（glob/grep/代码库探索）· 执行 ×3（shell/测试/git）· Web ×2 · 浏览器 ×9（Playwright，可选 `[browser]`）· SSH ×5 · 代码智能 ×3（类型检查/定义/引用）· 记忆 ×1 · 管理 ×1 · 示例 ×1。新增工具只需在 `claxcode/tools/` 放一个模块，自动发现并注册。

## 子代理

| 类型 | 权限 | 用途 |
|---|---|---|
| `explore` | 只读 | 代码库探索、答疑 |
| `planner` | 只读 | 方案设计、任务拆解 |
| `executor` | 全部工具 | 独立上下文执行实现 |

## API 服务

```bash
claxcode          # http://127.0.0.1:8000
```

- `POST/GET/GET{id}/DELETE /sessions` — 会话管理（对话自动持久化与恢复）
- `POST /sessions/{id}/chat` — SSE 流式对话（`thinking`/`message_delta`/`tool_call`/`tool_result`/`done` 事件）
- `GET /tools`、`POST /tools/invoke` — 工具查询与直接调用
- `POST /subagents`、`GET /subagents/{id}`、`POST /subagents/{id}/stream` — 子代理

## LLM 配置进阶

| Provider | `LLM_PROVIDER` | 说明 |
|---|---|---|
| OpenAI | `openai` | GPT-4o 等 |
| Anthropic | `anthropic` | 需 `pip install -e ".[anthropic]"` |
| OpenAI 兼容 | `generic_openai` | vLLM / LM Studio / DashScope 等 |
| Ollama | `ollama` | 本地模型，`LLM_CUSTOM_CONFIG={"ollama_options":{"num_ctx":8192}}` |
| 自定义 HTTP | `custom_http` | 请求模板 + 响应路径，适配任意 API |
| 代码注册 | 任意名字 | `register_custom_provider(name, MyProvider)` |

`custom_http` 示例（模板变量：`{api_key}` `{model}` `{messages}` `{temperature}` `{max_tokens}` `{tools}`）：

```env
LLM_PROVIDER=custom_http
LLM_CUSTOM_CONFIG={"request_template":{"url":"http://localhost:8000/chat","method":"POST","headers":{"Authorization":"Bearer {api_key}"},"body":{"model":"{model}","messages":"{messages}","stream":true}},"response_parser":{"content_path":"choices.0.delta.content"}}
```

## 与 Claude Code 的对比

覆盖其核心工作流的 **~80%**：Agentic 循环、流式输出、权限审批、快照回滚、技能、钩子、子代理、记忆、headless、`!`/`@`/`#` 前缀均已具备。主要差异：

- ❌ MCP（Model Context Protocol）— 规划中，下一优先级
- ❌ 多模态（图片输入）、IDE 插件
- ⚠️ 会话恢复为"自动续上次"，暂无 `/resume` 列表选择器
- ➕ 独有：SSH/浏览器工具、自定义 HTTP Provider 模板、SSE API 服务

## Roadmap

- [ ] MCP 客户端（stdio，发现并注册远端工具）
- [ ] 任务清单跟踪（TodoWrite 类工具）
- [ ] `/resume` 会话选择器
- [ ] 插件系统（`extensions/plugins.py`）

## 开发与测试

```bash
pytest          # 110 个测试
ruff check claxcode tests
mypy claxcode
```

目录结构、设计决策与扩展指南见 [AGENTS.md](AGENTS.md)。欢迎 Issue / PR。

## License

MIT

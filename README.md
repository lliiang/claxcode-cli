# ClaxCode

> 开源、自托管的终端 AI 编程助手：接入你选择的模型，在终端中完成代码阅读、编辑、测试与调试。

ClaxCode is an open-source agentic coding assistant for the terminal, inspired by Claude Code. It supports OpenAI-compatible providers, Anthropic, Ollama and custom HTTP APIs, with local sessions, memories, file snapshots and audit logs.

当前版本：`0.1.2`。项目仍处于早期阶段，欢迎 Issue、反馈和 PR。

## 核心特性

- **Agentic 工作流**：理解上下文、流式生成、调用工具、验证结果，最多自主迭代 10 轮。
- **模型自由选择**：OpenAI、OpenAI 兼容服务、Anthropic、Ollama、自定义 HTTP API。
- **终端原生体验**：`@` 文件模糊补全、命令与参数补全、中文路径、历史建议、多行输入。
- **权限与回滚**：5 种权限模式、逐项审批、编辑前快照、回滚和审计日志。
- **分层记忆**：会话恢复、全局用户偏好、项目滚动摘要、项目/全局长期记忆。
- **可扩展**：Skills、Shell Hooks、子代理和自动发现工具。
- **双前端**：交互式 CLI + FastAPI SSE 服务，支持非交互式脚本调用。
- **205 个自动化测试**：测试不需要真实 LLM 密钥或公网。

## 安装

要求：**Python 3.11+**，支持 Windows、macOS 和 Linux。

### 从 PyPI 安装

```bash
python -m pip install claxcode
```

### 从源码安装

在源码目录中执行：

```bash
python -m venv .venv

# Windows
.\.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

python -m pip install -e ".[dev]"
```

可选能力：

```bash
python -m pip install "claxcode[anthropic]"  # Anthropic SDK
python -m pip install "claxcode[browser]"    # 浏览器工具
playwright install chromium                  # browser extra 安装后执行
```

## 首次配置

直接运行根级初始化命令：

```bash
claxcode-cli init
```

按提示输入模型提供商、模型名称、接口地址和 API Key。API Key 使用隐藏输入；已有配置会先要求确认，不会直接覆盖。

全局配置文件位置：

- Windows：`%USERPROFILE%\.claxcode\.env`
- macOS / Linux：`~/.claxcode/.env`

配置示例：

```env
LLM_PROVIDER=generic_openai
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://your-endpoint/v1
LLM_MODEL=your-model
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=4096
```

支持的 Provider：

| Provider | `LLM_PROVIDER` | 说明 |
|---|---|---|
| OpenAI | `openai` | OpenAI API |
| OpenAI 兼容 | `generic_openai` | 其他 OpenAI 兼容端点 |
| DeepSeek | `deepseek` | 默认接口 `https://api.deepseek.com`，支持推理内容回传 |
| 阿里百炼 | `dashscope` | 阿里云百炼兼容模式 |
| 智谱 | `zhipu` | 智谱开放平台 |
| 月之暗面 | `moonshot` | Moonshot API |
| 火山方舟 | `volcengine` | 火山引擎方舟 |
| 硅基流动 | `siliconflow` | SiliconFlow API |
| Anthropic | `anthropic` | 需要 `anthropic` extra |
| Ollama | `ollama` | 本地模型，可通过 `LLM_CUSTOM_CONFIG` 设置 Ollama 选项 |
| 自定义 HTTP | `custom_http` | 使用请求模板与响应解析器适配其他 API |

配置覆盖优先级：

```text
--env 指定文件 > 当前项目 .env > 用户全局 .env
```

修改配置后重启 CLI。进入交互界面后可用 `/config` 查看当前生效配置。

> 不要把真实 API Key 提交到 Git。项目 `.env` 和用户全局配置都已设计为本地配置。

## 开始使用

```bash
# 在当前目录启动交互式助手
claxcode-cli

# 指定项目与权限模式
claxcode-cli --project /path/to/project --mode auto_safe

# 单发模式，适合脚本调用
claxcode-cli --print "总结一下这个项目的结构"

# 查看版本
claxcode-cli --version
```

交互示例：

```text
❯ 帮我重构 @claxcode/core/context.py，并补充类型标注
❯ 分析一下 @"docs/设计 说明.md"
❯ !git status
❯ #回答保持简洁，并优先给出可执行步骤
❯ /mode auto_safe
❯ /rollback list
```

输入规则：

- `@path`：引用项目内文本文件；支持模糊补全、中文路径和 `@"带 空格的路径"`。
- `!command`：直接执行 Shell；Ctrl+C 中止并返回输入提示。
- `#text`：保存一条全局自动记忆。
- Enter 提交，Alt+Enter 换行；Ctrl+C 清空非空输入，空输入时退出。
- `/` 补全内置命令、技能命令和常用参数。

## 权限与安全

| 模式 | 行为 |
|---|---|
| `ask`（默认） | 只读工具自动放行；写入和执行逐项询问 |
| `plan` | 只读规划，阻止写入和命令执行 |
| `auto_safe` | 允许读写和 Web，阻止命令执行 |
| `auto_edit` | 允许全部工具 |
| `yolo` | 完全无沙箱，谨慎使用 |

主 Agent 的写入工具会在执行前创建快照：

- `/rollback list`：查看快照。
- `/rollback [n]`：确认后回滚最近 n 个快照。
- `/audit [n]`：查看主 Agent 最近工具调用记录。

本地会话、记忆、快照和审计数据默认保存在 `.claxcode/` 或用户目录。**发送给模型的提示、代码和文件内容会离开本机并传输至对应模型服务商**，请根据项目敏感程度选择 Provider。

API 服务默认仅监听 `127.0.0.1`，当前没有身份认证。不要直接暴露到不可信网络；直接工具调用和 executor 子代理不经过主 Agent 的完整权限管线。

## 常用命令

| 命令 | 说明 |
|---|---|
| `/help` | 显示内置命令与技能命令 |
| `/version` | 查看版本号 |
| `/config` | 查看当前模型与运行配置 |
| `/mode [mode]` | 查看或切换权限模式 |
| `/clear` | 清除当前会话上下文 |
| `/project [list\|switch\|info]` | 项目信息、列表与完整切换 |
| `/memory` | 查看记忆总览 |
| `/memory list\|search\|learn\|forget` | 管理长期记忆和全局自动记忆 |
| `/compact` | 保存本次总结并融合更新项目滚动摘要 |
| `/init` | 初始化项目信息并生成 `CLAUDE.md` |
| `/skills [list\|reload\|create]` | 技能列表、热重载与创建 |
| `/tools` | 列出全部工具 |
| `/rollback [n\|list]` | 快照列表或回滚 |
| `/audit [n]` | 查看审计日志 |
| `/debug` | 切换调试输出 |
| `/exit` `/quit` | 退出 |

根级命令 `claxcode-cli init` 用于**全局模型配置**；交互命令 `/init` 用于**项目初始化**，两者用途不同。

## 分层记忆

| 层 | 存储 | 用途 |
|---|---|---|
| 会话消息 | SQLite | 每轮保存，CLI 启动时恢复项目最近会话 |
| 全局自动记忆 | `~/.claxcode/auto_memory.json` | 稳定的用户偏好和事实，下一轮即可生效 |
| 长期记忆 | SQLite | 保存项目或全局历史事件，按当前问题进行中文相关性检索 |
| 项目记忆 | SQLite + `CLAUDE.md` | 分别保存滚动项目状态与稳定项目约定 |

`/compact` 会分别生成本次总结和项目滚动摘要，并立即持久化清空后的会话。上下文过长时也会自动压缩早期消息。

## 工具与子代理

内置 **35 个工具**：

- 文件操作 ×7、搜索 ×3、执行 ×3。
- Web ×2、浏览器 ×9（可选）、SSH ×5。
- 代码智能 ×3，以及记忆、管理和示例工具。

子代理：

| 类型 | 权限 | 用途 |
|---|---|---|
| `explore` | 只读 | 代码库探索与答疑 |
| `planner` | 只读 | 方案设计与任务拆解 |
| `executor` | 全部工具 | 独立上下文执行实现 |

## Skills

一个 Skill 是包含 `SKILL.md` 的目录，可选 `tools.py` 注册专属工具。

加载顺序为内置 → 用户级 → 项目级，同名后者覆盖前者：

- 内置：`claxcode/skills/`
- 用户：`~/.claxcode/skills/`、`~/.agent/skills/`
- 项目：`.claxcode/skills/`、`.agent/skills/`、`skills/`

```text
/skills create my-skill
/skills reload
```

Skill 的 `tools.py` 会通过 `exec()` 加载，不要加载不可信来源的 Skill。

## Shell Hooks

在 `~/.claxcode/hooks.json` 或项目 `.claxcode/hooks.json` 中配置：

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

`match` 是工具名正则。Pre Hook 非零退出会阻止工具；超时或启动失败不会阻塞主流程。Hooks 本身是 Shell 命令，只使用可信配置。

## HTTP API

```bash
claxcode
# http://127.0.0.1:8000
GET /health -> ok
```

主要接口：

- `POST /sessions`、`GET /sessions`、`GET/DELETE /sessions/{id}`
- `POST /sessions/{id}/chat`：SSE 流式聊天
- `GET /tools`、`POST /tools/invoke`
- `POST /subagents`、`GET /subagents/{id}`、`POST /subagents/{id}/stream`

## 当前限制与计划

当前暂不支持：

- 图片/视觉输入。
- MCP 客户端。
- IDE 插件。
- `/resume` 会话列表选择器；CLI 目前自动恢复项目最近会话。

计划方向：MCP、任务清单工具、会话选择器和插件系统。欢迎围绕这些方向讨论与贡献。

## 开发与贡献

```bash
python -m pip install -e ".[dev]"
pytest
ruff check claxcode tests
mypy claxcode
```

贡献建议：

1. 先通过 Issue 描述问题或使用场景，再提交聚焦的小改动。
2. 新功能和缺陷修复应包含快速、无需真实 LLM 或公网的测试。
3. 遵循现有 async/await、类型标注和目录结构，不引入未声明依赖。
4. 修改命令或架构行为时同步更新 README 与 `AGENTS.md`。
5. 不提交 `.env`、`.claxcode/`、真实凭据或本机运行数据。

静态检查目前仍有历史存量告警；贡献代码至少不应新增告警。架构与扩展细节见 [AGENTS.md](AGENTS.md)。

### 发布到 PyPI

本地检查发布包：

```bash
python -m build
python -m twine check dist/*
```

仓库使用 `.github/workflows/publish.yml` 自动发布：推送 `v*` 标签，或在 GitHub Actions 中手动运行 **Publish to PyPI**。工作流会依次运行测试、构建和包检查，然后通过 OpenID Connect 发布，无需保存 PyPI Token。

发布前需要：

1. 更新 `pyproject.toml` 中的版本号并提交。
2. 在 PyPI 配置 Trusted Publisher：项目 `claxcode`、所有者 `lliiang`、仓库 `claxcode-cli`、工作流 `publish.yml`、环境 `pypi`。
3. 在 GitHub `Settings → Environments` 创建 `pypi` 环境。
4. 推送版本标签，例如 `git tag v0.2.0 && git push origin v0.2.0`。

## 常见问题

**Windows 提示 `claxcode-cli` 不是命令？**

确认 Python 的 `Scripts` 目录已加入 PATH，或使用：

```bash
python -m claxcode.cli
```

**终端出现乱码？**

CLI 会尝试启用 UTF-8。仍有问题时建议使用 Windows Terminal，或先执行 `chcp 65001`。

**如何使用有头浏览器？**

直接要求 Agent 使用有头浏览器，或在配置中设置 `BROWSER_HEADLESS=false`。

**如何中止耗时操作？**

输入或工具执行期间可使用 Ctrl+C；SSH 等长任务会轮询取消标记。

## License

MIT

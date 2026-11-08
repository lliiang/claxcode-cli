# AGENTS.md — ClaxCode

本文面向首次接触本仓库的 AI 编程代理，说明当前实现、开发命令和修改约定。阅读代码时以实际实现为准；`README.md` 是主要的人类可读说明，本文侧重开发与架构细节。

## 项目概览

ClaxCode 是一个用 Python 编写的开源、自托管 Agentic 编程助手，灵感来自 Claude Code。两个前端共享同一套 Agent、LLM Provider、工具、权限和记忆系统：

- **交互式 CLI**（`claxcode-cli`）：REPL 终端助手，也支持 `--print/-P` 单发模式。斜杠命令集中定义在 `claxcode/cli.py` 的 `_build_commands()` 中，`/help` 由该表生成。
- **HTTP API**（`claxcode`）：FastAPI 应用，通过 SSE 流式返回聊天事件。

核心循环位于 `claxcode/core/agent.py`：收集上下文 → 流式调用 LLM → 执行工具 → 发出验证标记并进入下一轮。每条用户消息最多迭代 10 次；没有工具调用时结束。主 Agent 会把系统提示、项目上下文、Skills、自动记忆、项目记忆及相关长期记忆组合进上下文。

当前版本**不支持图片/视觉输入**；CLI 的 `@path` 会跳过常见图片扩展名。

## 技术栈与关键配置

- Python **>= 3.11**；`pyproject.toml` 使用 **hatchling** 构建 wheel，包名为 `claxcode`，版本为 `0.1.0`。
- **FastAPI + Uvicorn**：HTTP API 与 SSE（`StreamingResponse`）。
- **Pydantic v2 + pydantic-settings**：配置和 API 数据模型。
- **SQLAlchemy 2.0 异步 API + aiosqlite**：默认使用本地 SQLite。
- **httpx**：OpenAI 兼容、Ollama、自定义 HTTP Provider 以及 Web 工具的 HTTP 请求；OpenAI Provider 不依赖 `openai` SDK。
- **prompt-toolkit**：CLI 的 `@` 文件模糊补全和 `/` 命令补全。
- **paramiko**：SSH 工具。
- **Playwright**：可选浏览器工具，延迟导入，通过 `browser` extra 安装。
- **pytest + pytest-asyncio + pytest-httpx**：测试；**ruff** 和 **mypy**：静态检查。

关键文件：

| 文件/目录 | 作用 |
|---|---|
| `pyproject.toml` | 构建、依赖、console scripts、pytest、ruff、mypy 的唯一主要配置 |
| `.env.example` | 最小环境变量模板；复制为 `.env` 后填写 Provider 和密钥 |
| `claxcode/config.py` | 全部环境驱动设置；`.env` 中未知变量会被忽略 |
| `README.md` | 中文使用说明、功能介绍和示例 |
| `AGENT.md` | 注入 Agent 的项目上下文；由根级 `claxcode-cli init` 生成 |
| `.claxcode/` | 本地运行时状态：数据库、快照、审计日志、CLI 会话指针等，不应提交 |

仓库没有 `package.json`、锁文件、Makefile 或 Dockerfile。`.github/workflows/publish.yml` 提供 PyPI 发布 CI：推送 `v*` 标签或手动触发，运行测试和构建后通过 OIDC 发布，使用 GitHub 环境 `pypi`。

## 安装、构建与运行

在仓库根目录执行。 editable 安装不需要单独的构建步骤。

```bash
python -m venv .venv
# Windows cmd / PowerShell：
.\.venv\Scripts\activate
# Unix  shells：
source .venv/bin/activate

pip install -e ".[dev]"
cp .env.example .env       # 然后编辑 .env
```

可选依赖：

```bash
pip install -e ".[anthropic]"  # AnthropicProvider 需要 anthropic SDK
pip install -e ".[browser]"    # 浏览器工具需要 Playwright；还需可用的 Chromium
```

`pyproject.toml` 也声明了 `openai` extra，但当前 OpenAI/OpenAI 兼容 Provider 直接使用 httpx，不导入该 SDK。

启动方式：

```bash
# FastAPI 服务，默认 http://127.0.0.1:8000；GET /health 返回纯文本 ok
claxcode
# 等价：python -m claxcode.main

# 交互式 CLI
claxcode-cli --project . --mode ask
# 等价：python -m claxcode.cli --project . --mode ask

# 非交互单发模式；正文走 stdout，工具事件走 stderr
claxcode-cli --print "总结这个项目的结构"
```

`claxcode` 和 `claxcode-cli` 分别映射到 `claxcode.main:run`、`claxcode.cli:main`。Uvicorn 的 host、port 和 reload 由环境设置控制。

## 运行时架构

```text
CLI / FastAPI API
       │
       ▼
Agent（上下文组装、最多 10 轮循环）
       ├── LLMProvider（流式文本与工具调用）
       ├── ToolRegistry（内置及 Skill 工具）
       │     └── 权限 → PreToolUse → 写前快照 → 工具 → PostToolUse → 审计
       └── ContextManager（历史恢复、估算、压缩）
              │
              ▼
SQLite 会话/子代理/长期记忆/项目记忆 + 本地 JSON 自动记忆
```

### CLI 行为

- `!cmd`：直接调用 `run_shell`，Ctrl+C 会终止子进程并返回提示；`@path` 或 `@"带 空格的路径"`：把项目内 UTF-8 文本文件内容（最多 8000 字符）附加到提示，重复引用只内联一次，加载失败会在 stderr 给出原因；`#text`：写入自动记忆。
- prompt_toolkit 不可用或没有真实控制台时退回普通 `input()`。文件索引最多缓存 5000 个路径，30 秒过期，并排除依赖/缓存目录。`@` 支持模糊文件补全，`/` 支持命令和常用参数补全；输入历史存于 `.claxcode/cli_history`，Enter 提交、Alt+Enter 换行、Ctrl+C 清空非空输入。
- 每个项目的 `.claxcode/cli_session` 保存最近会话 UUID；每轮结束后保存消息，下次启动自动恢复，`/clear` 清空上下文。会话中没有 `/project` 或 `/init`；根级 `claxcode-cli init` 只记录项目名称、描述和初始化时间，`init --global` 配置全局模型。`claxcode-cli project`/`project list` 列出项目并按编号进入，也可用 `project <目录>` 或 `--project` 直接进入。命令参数支持成对引号和 Windows 路径，覆盖已有 `AGENT.md` 前需要确认。
- `ask` 模式的交互审批支持 `y`（允许一次）、`a`（本会话始终允许该工具）、`N`（拒绝）；切换 `/mode` 会清空自动批准集合。
- Ctrl+C 设置全局工具取消标记；长任务（例如 SSH）轮询该标记，Agent 在处理下一条用户消息前重置它。

### API 表面

- `POST /sessions`、`GET /sessions`、`GET /sessions/{id}`、`DELETE /sessions/{id}`：会话管理。
- `POST /sessions/{id}/chat`：SSE 聊天；事件包括 `thinking`、`message_delta`、`tool_call`、`tool_result_start`、`tool_result`、可选 `debug`、`done`。
- `GET /tools`、`POST /tools/invoke`：列出工具、直接调用工具。
- `POST /subagents`、`GET /subagents/{task_id}`、`POST /subagents/{task_id}/stream`：创建、查询和流式运行子代理任务。
- `GET /health`：健康检查。

每次 API 聊天请求都会新建 Agent、从数据库恢复该会话消息，并在流结束后重新保存。FastAPI lifespan 启动时初始化数据库。

## 代码组织

```text
claxcode/
├── main.py                 # FastAPI app、路由注册、/health、Uvicorn 启动
├── cli.py                  # REPL、单发模式、斜杠命令、审批与 CLI 持久化
├── cli_completion.py       # @ 文件和 / 命令补全
├── config.py               # pydantic-settings 全局 settings
├── api/                    # session、chat、tools、subagents 路由
├── models/                 # API 的 Pydantic 请求/响应模型
├── core/
│   ├── agent.py            # 主 Agent 循环及工具执行管线
│   ├── models.py           # LLMProvider 抽象和各 Provider
│   ├── context.py          # 消息历史、Token 粗估、摘要压缩、恢复清理
│   └── checkpoint.py       # 写前文件快照、manifest、列表与回滚
├── tools/                  # Tool 基类、注册表及自动发现的内置工具
├── memory/
│   ├── session_store.py    # SQLAlchemy ORM、init_db、会话和子代理持久化
│   ├── long_term.py        # 长期记忆检索、导入导出等
│   ├── project_memory.py   # 项目记录与摘要
│   ├── project_context.py  # AGENT.md / .claxcode/context.md 加载
│   └── auto_memory.py      # ~/.claxcode/auto_memory.json，最多 50 条
├── extensions/
│   ├── skills.py           # Skill 加载、覆盖、命令和 tools.py 动态注册
│   ├── hooks.py            # PreToolUse / PostToolUse shell hooks
│   ├── mcp.py              # 占位实现，仅返回空工具列表
│   └── plugins.py          # 占位实现
├── security/
│   ├── permissions.py      # 五种权限模式
│   └── audit.py            # .claxcode/audit.jsonl 审计日志
├── subagents/              # explore、planner、executor 及独立上下文基类
└── skills/                 # task-workflow、bug-fix、code-review、python-refactor

tests/                      # 按 api/core/tools/memory/security/extensions 分组的 pytest 套件
```

### 工具系统

- 工具继承 `claxcode/tools/base.py` 的 `Tool`，定义 `name`、`description`、JSON Schema `input_schema`、`category`、`required_permissions`，实现 `async execute(**kwargs) -> str`。
- `@tool` 在 `claxcode/tools/registry.py` 中把实例注册进全局 `registry`。
- `claxcode/tools/__init__.py` 使用 `pkgutil` 自动导入包内模块（排除 base、registry 和 `__init__`）；新增工具模块通常不需要手工登记。两个入口都导入 `claxcode.tools` 以触发发现。
- 当前有 **35 个内置工具**：文件操作 7、搜索 3、执行 3、Web 2、浏览器 9、SSH 5、代码智能 3，以及 `remember_fact`、`admin_add_tool`、`calculate`。
- 浏览器工具共享 actor 式持久会话，同一页面可跨工具调用和对话轮次连续使用。Playwright 或 Chromium 不可用时，相应测试会跳过。
- 工具结果保持普通字符串；新增工具应把预期异常转换成错误字符串，不让 `execute()` 直接向调用方抛出异常。

### LLM Provider

`claxcode/core/models.py` 定义 `LLMProvider.stream_chat(messages, tools)`，以异步迭代器产生文本块或工具调用字典。`get_provider()` 支持：

- `openai`：OpenAI API，httpx 实现。
- `generic_openai`：vLLM、LM Studio 等 OpenAI 兼容端点。
- `deepseek`、`dashscope`、`zhipu`、`moonshot`、`volcengine`、`siliconflow`：国内供应商预设，复用 OpenAI 兼容 Provider 并自动选择默认端点；OpenAI 流式解析按工具索引拆分调用，并保存、回传 `reasoning_content`。
- `anthropic`：Anthropic SDK；未安装依赖时退回 `DummyProvider`。
- `ollama`：原生 `/api/chat`，`LLM_CUSTOM_CONFIG` 可传 `ollama_options`。
- `custom_http`：通过 `request_template` 和 `response_parser` 适配自定义流式 HTTP API。
- 运行时通过 `register_custom_provider(name, cls)` 注册的其他 Provider。

未知名称会退回 `DummyProvider`，使应用仍能启动并报告配置问题。

### 上下文与持久化

- `init_db()` 用 `Base.metadata.create_all` 创建 `sessions`、`subagent_tasks`、`long_term_memories`、`project_memories`；**没有数据库迁移系统**。
- 默认数据库为 `./.claxcode/claxcode.db`。会话消息以 JSON 存在 `sessions.messages`，系统提示不持久化。
- `ContextManager.restore()` 会清理不完整的工具调用/结果配对，避免 Provider 拒绝孤立消息。
- Token 数是粗略字符估算（`len(text) // 3 + 1`）。超过阈值时，主 Agent 调用 LLM 总结最旧的一半消息；新增消息时的硬上限保护会直接丢弃最旧消息。
- 系统提示可由 `~/.claxcode/system_prompt.md` 覆盖；项目上下文依次尝试 `AGENT.md`、`.claxcode/context.md`。
- 记忆职责分层：`~/.claxcode/auto_memory.json` 只保存稳定的全局用户偏好/事实；长期记忆保存项目或全局历史事件；项目记忆保存滚动状态摘要。自动记忆和长期记忆每轮动态刷新，避免当前会话写入后不生效或重复注入。
- 长期记忆检索使用“当前项目 + 全局”作用域，支持中文词语与二字片段相关性排序，无匹配时退回少量近期记忆；项目路径在写入和查询时统一标准化。
- `/compact` 分别生成本次总结与融合旧状态的项目滚动摘要，写入长期记忆和项目记忆后立即持久化清空后的会话；项目未初始化时也会自动创建摘要记录。

## 环境变量

所有设置见 `claxcode/config.py`；下表默认值来自代码，而不是仅来自 `.env.example`。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `LLM_PROVIDER` | `openai` | Provider 名称或运行时注册的自定义名称 |
| `LLM_API_KEY` / `LLM_BASE_URL` | 空字符串 | API 密钥 / 端点 |
| `LLM_MODEL` | `gpt-4o` | 模型名 |
| `LLM_TEMPERATURE` / `LLM_MAX_TOKENS` | `0.2` / `4096` | 生成参数 |
| `LLM_CUSTOM_CONFIG` | 空字符串 | JSON；用于 Ollama 选项或自定义 HTTP 模板 |
| `DATABASE_URL` | `sqlite+aiosqlite:///./.claxcode/claxcode.db` | SQLAlchemy 异步连接串 |
| `SNAPSHOTS_DIR` | `./.claxcode/snapshots` | 写前快照目录 |
| `PROJECT_CONTEXT_FILE` | `AGENT.md` | 项目上下文文件名 |
| `PERMISSION_MODE` | `ask` | `ask` / `auto_edit` / `plan` / `auto_safe` / `yolo` |
| `MAX_CONTEXT_TOKENS` | `128000` | 粗略上下文预算 |
| `CONTEXT_COMPRESSION_THRESHOLD` | `0.85` | 触发压缩的预算比例 |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | API 监听地址 |
| `CLAXCODE_DEBUG` | `false` | 调试事件、SQL echo、Uvicorn reload |
| `TOOL_TIMEOUT` | `60` | 工具相关默认超时配置 |
| `BROWSER_HEADLESS` | `true` | 新浏览器会话的默认模式 |

CLI 在导入项目模块前加载模型配置，优先级为 `--env` 指定文件 > 当前目录 `.env` > `~/.claxcode/.env`；修改 CLI 的导入顺序时保留这一约束（ruff 对 `cli.py` 特意忽略 E402）。`claxcode-cli init --global` 交互创建全局配置，API Key 使用隐藏输入，覆盖已有文件前需确认；不带 `--global` 时只询问项目描述并初始化当前目录。版本可通过 `/version` 或 `claxcode-cli --version/-v` 查看。

## 扩展点

- **新工具**：在 `claxcode/tools/` 新增模块，继承 `Tool` 并使用 `@tool`；为文件、Shell、Web 等能力准确声明权限。
- **新 Provider**：继承 `LLMProvider`，在 `get_provider()` 加分支，或在运行时调用 `register_custom_provider()`。
- **新 Skill**：目录中放置 `SKILL.md`（`# Name`、`## Description`、`## Instructions`，可选 `## Commands`）和可选 `tools.py`。加载顺序为内置 `claxcode/skills/` → 用户 `~/.claxcode/skills/`、`~/.agent/skills/` → 项目 `.claxcode/skills/`、`.agent/skills/`、`skills/`；同名后者覆盖前者。CLI 支持 `/skills create` 和 `/skills reload`。
- **Hooks**：在 `~/.claxcode/hooks.json` 或项目 `.claxcode/hooks.json` 配置 `PreToolUse`/`PostToolUse`。`match` 是工具名正则；命令从 stdin 收到 JSON，并获得 `CLAXCODE_TOOL_NAME`、`CLAXCODE_TOOL_ARGS`。Pre hook 非零退出会阻止工具；启动失败或 30 秒超时不阻塞主流程。
- **子代理**：`explore` 和 `planner` 仅开放六个只读搜索/读取工具，分别最多 8 和 5 轮；`executor` 开放全部工具，最多 10 轮。子代理拥有独立上下文。

## 开发约定与代码风格

遵循 README 中的原则：**最少代码、最简单实现**。

1. 只实现当前需求，不做顺手重构或投机性配置。
2. 扁平优于嵌套，优先提前返回；三行相似代码优于过早抽象。
3. 在根因处修复问题，及时删除死代码。
4. 新功能和缺陷修复应附快速、无需真实 LLM 或外部网络的测试。
5. 使用现有 async/await、类型标注、`pathlib.Path` 和绝对导入风格，避免引入未在 `pyproject.toml` 声明的新依赖。

语言约定：`README.md`、CLI 输出、错误信息和多数 LLM 提示使用中文；模块 docstring 多数为英文，代码内注释中英混合。编辑时匹配所在文件，新增用户-facing 文本通常使用中文。

静态检查命令：

```bash
ruff check claxcode tests
mypy claxcode
```

ruff 配置为行宽 100、Python 3.11，规则 `E,F,I,N,W,UP,B,C4,SIM`；mypy 为 strict。**当前全量静态检查基线并不干净**：本次验证 ruff 报告 36 项、mypy 报告 104 项（含缺失可选依赖/类型 stub 等问题）。修改时不要新增告警，并区分存量问题与自己的改动。

## 测试策略

```bash
pytest                              # 全量
pytest tests/test_core/test_agent_permissions.py
pytest tests/test_tools/test_file_operations.py -k write
```

`pyproject.toml` 设置 `testpaths = ["tests"]`、`asyncio_mode = "auto"` 和 `asyncio_default_fixture_loop_scope = "function"`，异步测试无需统一额外装饰器（部分旧测试仍显式使用 `@pytest.mark.asyncio`）。

- `tests/conftest.py` 的 `client` fixture 调用 `init_db()`，再用 httpx `ASGITransport` 和 `AsyncClient` 直接测试 FastAPI，不启动真实端口。
- 测试目录按被测模块分组。新工具、Provider、权限或扩展功能应在相邻测试目录添加同风格测试。
- 使用 `monkeypatch`、临时目录和假 Provider/会话隔离外部依赖；`pytest-httpx` 可用于出站 HTTP mock。测试不得要求真实 LLM 密钥或公网。
- 浏览器集成测试只使用本地 `data:` URL；Playwright/Chromium 不可用时跳过。
- 本次实际验证结果：**209 个测试全部通过**（`209 passed in 9.87s`）。README 内其他测试数量是历史值，以 pytest 实际收集结果为准。

## 安全注意事项

主 Agent 的权限模式：

| 模式 | 行为 |
|---|---|
| `ask` | 仅声明 `read` 的工具自动放行；其他工具需要审批。API 聊天没有审批回调，因此这些工具会被阻止 |
| `plan` | 阻止需要 `write` 或 `execute` 的工具 |
| `auto_safe` | 阻止需要 `execute` 的工具，允许读、写和 Web 工具 |
| `auto_edit` / `yolo` | 当前实现均放行全部工具；`yolo` 应视为完全无沙箱 |

主 Agent 的 `_execute_tool()` 顺序为：权限检查 → Pre hook → 对带 `path` 参数的写工具创建快照 → 执行 → Post hook → 审计。快照只覆盖执行前已存在的文件，位于 `.claxcode/snapshots/<session>/<timestamp>/`，原始路径记录在 `manifest.json`；CLI `/rollback` 使用这些 manifest 恢复。允许和被阻止的主 Agent 工具调用都会尝试写入 `.claxcode/audit.jsonl`。

必须注意以下边界：

- `POST /tools/invoke` 直接执行工具，**不经过**主 Agent 的权限、hooks、快照和审计管线。
- 子代理基类也直接执行其允许列表中的工具；`executor` 的全部工具调用不经过主 Agent 管线。
- CLI 的 `!cmd` 是直接 Shell 执行入口，不经过交互审批。
- `run_shell`、`git_command` 可执行任意命令；`admin_add_tool` 会写入工具代码；Skill 的 `tools.py` 通过 `exec()` 加载；Hooks 本身也是 Shell 命令。不要加载不可信配置或 Skill。
- API 未实现身份认证，默认仅绑定 `127.0.0.1`。不要在不可信网络中直接暴露，尤其不要与直接工具调用或 executor 组合暴露。
- `.env`、`.claxcode/`、虚拟环境和缓存均由 `.gitignore` 排除。`.env` 虽未在当前索引中跟踪，但曾出现在 Git 历史中；其中曾使用的真实密钥必须轮换，不能仅依赖删除文件。

## 部署与已知限制

- 应用部署仍是本地 editable 安装后用 console script 启动 Uvicorn 或 CLI；没有容器、进程管理或生产部署工具。PyPI 发布由 GitHub Actions 负责。
- 数据库仅自动建表，没有 Alembic 等迁移机制；修改 ORM 时需考虑既有本地数据库。
- MCP 和插件系统仍是 stub，不能当作已可用能力。
- 无视觉输入、无 `/resume` 会话选择器；CLI 只自动恢复项目最近一次会话。
- `.claxcode/` 是本地状态，不是源码；调试问题时可检查数据库、快照和审计日志，但不要提交这些文件。

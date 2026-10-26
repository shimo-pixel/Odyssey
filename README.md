# Odyssey · 平行世界决策推演

Odyssey（后端包名 PRDS，Parallel Reality Decision Simulator）是基于大语言模型与知识图谱的决策推演应用。输入当前处境和目标，系统生成多种应对策略，让策略分支沿事件时间线并行演化，再比较分支状态、评分与决策路径。

支持知识库文档检索、分支知识图谱、推演暂停与事件注入、历史记录，以及独立的模型对话。结果用于辅助比较策略，不能视为真实世界的成功概率。

架构、模块职责和数据流见 [项目架构说明](docs/ARCHITECTURE.md)。

## 技术组成

| 组件 | 实现 | 默认端口 |
| --- | --- | --- |
| 前端 | 原生 JavaScript ES Modules、Tailwind CSS，Python 静态服务器 | 3000 |
| 应用 API | FastAPI、Pydantic、SQLAlchemy、SQLite、LiteLLM | 8000 |
| 知识库 | 仓库内定制的 LightRAG，提供文档索引、检索和图谱界面 | 9621 |
| 可选数据库 | Docker Compose 中的 Neo4j | 7474 / 7687 |

浏览器通过 `http://localhost:8000/api` 访问应用 API；知识图谱通过后端 `/lightrag/` 代理访问 LightRAG。标准启动仅监听 `127.0.0.1`，面向本机单用户使用。远程共享需另行配置身份校验和访问控制。

## 环境要求

- Python 3.11 或更高版本，包含 pip 与 venv。Debian / Ubuntu 若创建虚拟环境失败，先安装对应版本的 `python3-venv`。
- Bash 和 curl：用于启动脚本。
- Bun：首次构建 LightRAG WebUI 时需要。
- Node.js / npm：仅修改或重新生成主前端 Tailwind CSS 时需要；仓库已包含 `frontend/css/tailwind.css`。
- 模型服务的 API Key；知识库索引还需要可用的 Embedding 服务。

以下命令均从仓库根目录执行，适用于 Linux / macOS。

## 首次安装

### 1. 安装 Python 依赖

后端与 LightRAG 可以共用根目录虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
python -m pip install -e './backend[dev]' -e './backend/LightRAG[api]'
```

请安装仓库内的 LightRAG 源码，以保留本项目使用的工作区与图谱嵌入功能。

### 2. 构建知识图谱界面

```bash
cd backend/LightRAG/lightrag_webui
bun install --frozen-lockfile
bun run build:bun
cd ../../..
```

产物位于 `backend/LightRAG/lightrag/api/webui/`。未构建时，LightRAG API 与图谱网页的可用状态可能不同。

### 3. 创建配置

```bash
cp -n backend/.env.example backend/.env
mkdir -p backend/data/lightrag
```

编辑 `backend/.env`，填写模型配置；也可以启动后在页面的模型设置中配置。下列模型名来自项目默认配置，请使用你的服务实际支持的模型。

```dotenv
OPENAI_API_KEY=你的模型服务密钥
PRDS_LLM_MODEL=gpt-4o-mini
PRDS_LLM_MODEL_ANALYSIS=gpt-4o
# 使用兼容接口时填写对应地址与 provider
# PRDS_LLM_API_BASE=https://your-provider.example/v1
# PRDS_LLM_PROVIDER=openai
```

使用 DeepSeek 时，将密钥填入 `DEEPSEEK_API_KEY`，并设置对应的 `PRDS_LLM_MODEL`、`PRDS_LLM_MODEL_ANALYSIS` 和 `PRDS_LLM_API_BASE`。

首次启动前，新建 `backend/data/lightrag/.env`，可使用以下最小配置，替换密钥与服务地址：

```dotenv
LLM_BINDING=openai
LLM_BINDING_HOST=https://api.openai.com/v1
LLM_BINDING_API_KEY=你的模型服务密钥
LLM_MODEL=gpt-4o-mini
EMBEDDING_BINDING=openai
EMBEDDING_BINDING_HOST=https://api.openai.com/v1
EMBEDDING_BINDING_API_KEY=你的向量服务密钥
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536
EMBEDDING_SEND_DIM=false
```

LLM 与 Embedding 可以使用不同服务。Embedding 模型与维度必须匹配；对话服务地址未必提供向量接口。更多选项见 [LightRAG 说明](backend/LightRAG/README-zh.md)。

### 4. 启动与停止

```bash
source .venv/bin/activate
export NO_PROXY="localhost,127.0.0.1${NO_PROXY:+,$NO_PROXY}"
export no_proxy="$NO_PROXY"
./scripts/start.sh
```

脚本依次启动 LightRAG、后端与前端，并等待就绪。LightRAG 启动失败时仍会尝试启动后端与前端，需检查知识库状态和日志。

上述 `NO_PROXY` 配置让本机服务间的请求绕过系统 HTTP 代理；如果未启用代理，也可以保留。LightRAG 首次启动可能联网下载分词词表。

| 地址 | 用途 |
| --- | --- |
| http://localhost:3000 | 应用入口 |
| http://localhost:8000/docs | 应用 API 文档 |
| http://localhost:8000/api/health | 应用健康检查与模型配置状态 |
| http://localhost:8000/api/kb/status | LightRAG 连通状态 |
| http://localhost:8000/lightrag/webui/ | 代理后的 LightRAG 界面 |

```bash
# 查看日志
tail -n 80 backend/data/logs/backend.log
tail -n 80 backend/data/logs/lightrag.log
tail -n 80 backend/data/logs/frontend.log

# 停止服务
./scripts/stop.sh
```

停止脚本会按进程名并清理 3000、8000、9621 端口，运行前请确认这些端口没有被其他项目使用。

也可以在三个终端分别激活 `.venv`，再各自运行一个脚本：

```bash
./scripts/run-lightrag.sh
./scripts/run-backend.sh
./scripts/run-frontend.sh
```

## 使用流程

1. 打开应用，在模型设置中添加模型并设为默认模型。
2. 需要外部材料时，在知识库创建分类、上传文档，等待索引完成。
3. 新建推演，填写背景、当前状态与目标，选择知识库、策略数量和事件数量。
4. 查看事件进度与分支演化。进入分支推演阶段后，可暂停、注入事件，再继续运行。
5. 完成后查看策略排名、决策轨迹与分支图谱；历史记录可从侧栏重新打开。

| 前端路由 | 功能 |
| --- | --- |
| `#simulate` / `#simulate/<id>` | 新建推演 / 查看已有推演 |
| `#chat` / `#chat/<id>` | 模型对话 / 已有会话 |
| `#kb` / `#kb/<id>` | 知识库列表 / 分类详情及图谱 |
| `#settings` / `#model` | 打开设置或模型弹窗 |

旧的 `#history`、`#monitor`、`#results` 路由会转到推演页，`#knowledge` 会转到知识库。

页面保存的模型配置持久化到 SQLite，并同步部分配置到 LightRAG 工作目录的 `.env`。修改模型或密钥后需重启 LightRAG；已有 Embedding 配置应单独检查。未配置有效密钥时可以查看页面和 API，但不能完成真实模型调用。

## 推演状态与故障处理

- 推演页选择的模型用于本次输入分析、事件规划、策略、预测及总结；任务启动后固定模型配置。LightRAG 的索引与 Embedding 仍使用知识库自己的配置。
- 在分支推演阶段可暂停，暂停后添加事件并继续；注入事件作用于下一轮。最后一个事件开始后无法再暂停。
- 必需的模型输出或知识库操作失败会停止任务并显示失败阶段。总结生成失败时保留已计算结果并显示警告；检索成功但没有相关材料时也会提示依据不足。
- “停止推演”取消运行或暂停中的任务。删除时先等待任务退出，再清理分支图谱、删除记录；图谱服务不可用时保留记录，可稍后重试删除。
- 服务重启后，未结束的任务标记为“已中断”。“重新运行”创建新任务并保留旧记录，不自动重放途中注入的事件，也不会自动重复计费。模型已删除时需在重试区域重新选择模型。
- 检查点仅用于诊断，本版本不支持断点续跑。默认关闭后端热重载；开发时可执行 `./scripts/run-backend.sh --reload`。
- 状态请求超时或断连时页面会提示并退避重试，连续五次失败后暂停刷新，可手动重连；网络异常不会改变后台任务状态。

## 常用配置

完整列表见 [backend/.env.example](backend/.env.example) 与 [config.py](backend/src/prds/config.py)。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PRDS_DEFAULT_AGENT_COUNT` | `4` | 默认策略分支数量 |
| `PRDS_DEFAULT_MAX_EVENTS` | `6` | 默认事件数量 |
| `PRDS_KBSIM_MAX_STEPS` | `200` | 策略数量 × 事件数量上限，超过返回 422 |
| `PRDS_KBSIM_MAX_CONCURRENT_BRANCHES` | `8` | 分支并发上限 |
| `PRDS_KBSIM_REINDEX_EVERY` | `1` | 每隔多少事件更新分支知识库 |
| `PRDS_KBSIM_KEEP_BRANCHES` | `true` | 保留分支工作区以便浏览图谱 |
| `PRDS_DATABASE_URL` | `sqlite+aiosqlite:///./prds.db` | 数据库连接 |
| `PRDS_LIGHTRAG_URL` | `http://127.0.0.1:9621` | LightRAG 服务地址 |

启动脚本以 `backend/` 为后端工作目录，因此默认数据库位于 `backend/prds.db`。日志位于 `backend/data/logs/`，知识库工作目录为 `backend/data/lightrag/`。

## API 概览

| 路径 | 功能 |
| --- | --- |
| `/api/health`、`/api/config` | 健康检查与公开配置 |
| `/api/simulations` | 创建推演、历史列表 |
| `/api/simulations/{id}` | 推演状态、删除记录 |
| `/api/simulations/{id}/result` | 已完成的推演结果 |
| `/api/simulations/{id}/pause`、`resume`、`events` | 暂停、继续、用户事件 |
| `/api/simulations/{id}/cancel`、`retry` | 停止任务、重新运行（可传新的 `model_id`） |
| `/api/simulations/{id}/knowledge-graph` | 分支图谱信息 |
| `/api/kb/status`、`categories`、`documents` | 知识库状态、分类、文档 |
| `/api/llm-settings`、`/api/llm-models` | 模型设置与模型目录 |
| `/api/chat/...` | 对话及会话管理 |
| `/lightrag/...` | LightRAG 同源代理 |

请求格式与支持的方法以运行中的 `/docs` 为准。创建推演可传 `config.model_id`；与旧 `llm_model` / `llm_model_analysis` 覆盖字段互斥。状态和结果包含公开的 `model_info`、结构化 `warnings`，失败状态另带 `failure`。旧历史缺失模型信息时显示“未记录”。

## 开发与验证

```bash
source .venv/bin/activate
cd backend
python -m pytest -v
```

前端回归检查（本次使用 Node.js 24 验证）：

```bash
cd frontend
npm test
npm run check:i18n
```

浏览器离线验收使用受控 API，不调用真实模型：先在虚拟环境安装可选工具 `python -m pip install playwright` 并执行 `python -m playwright install chromium`，再从仓库根目录运行 `python frontend/scripts/check-simulation-ui.py`。Linux 需安装 Chromium 所需系统库。

确认启动状态：

```bash
curl -fsS http://localhost:3000/ -o /dev/null
curl -fsS http://localhost:8000/api/health
curl -fsS http://localhost:8000/api/kb/status
```

修改主前端 Tailwind 样式时：

```bash
cd frontend
npm ci
npm run build:css
# 开发时可用 npm run watch:css
```

## 目录结构

```text
Odyssey/
├── backend/
│   ├── src/prds/
│   │   ├── api/          # 推演、对话与模型 API
│   │   ├── kbsim/        # 策略分支、事件、状态演化与结果汇总
│   │   ├── kb/           # LightRAG 客户端、代理和配置同步
│   │   ├── llm/          # 模型调用与 provider 适配
│   │   └── storage/      # SQLite 持久化
│   ├── LightRAG/         # 定制知识库服务与 WebUI 源码
│   ├── tests/            # 应用后端测试
│   ├── data/             # 运行数据与日志（忽略提交）
│   └── .env.example
├── frontend/             # 静态 SPA 与本地 CSS
├── scripts/              # 启动、停止脚本
├── docs/examples/        # 示例场景
└── docker-compose.yml    # 可选 Neo4j 服务
```

场景示例见 [startup.txt](docs/examples/startup.txt)。Neo4j 可通过 `docker compose up -d` 启动；该 Compose 文件只启动 Neo4j，应用仍需使用上述脚本启动。默认文件存储方案不要求运行 Neo4j。

## 常见问题

- **`uvicorn not found` / `lightrag-server not found`**：确认依赖已安装，并在运行 `start.sh` 前激活根目录 `.venv`。LightRAG 脚本优先查找自身 `.venv`，其次查找 `PATH`。
- **页面能打开但不能推演**：检查 `/api/health` 的 `llm_configured`，再检查模型密钥、地址与模型名。健康检查不会验证密钥是否真实有效。
- **知识库离线或上传失败**：检查 `/api/kb/status` 与 `lightrag.log`，确认 Embedding 配置及网络连通性。
- **图谱页面无法显示**：确认已构建 LightRAG WebUI，并重启 LightRAG。
- **前端无法访问后端**：默认地址在 `frontend/config.js`，也可在该脚本加载前设置 `window.PRDS_API_BASE`。远程访问时 `localhost` 指浏览器所在机器；同时需要按实际来源配置后端 CORS。
- **端口冲突**：启动前确认 3000、8000、9621 未被其他服务占用。

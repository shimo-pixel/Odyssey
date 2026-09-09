# PRDS - Parallel Reality Decision Simulator

多智能体平行世界决策推演系统。通过构建 N 个策略不同的智能体，在随机事件驱动的模拟环境中竞争推演，输出最可能成功的决策轨迹。

## 仓库结构

```
Odyssey/
├── backend/              # FastAPI API
│   ├── src/prds/
│   ├── LightRAG/         # 知识库 sidecar（本地已有）
│   ├── data/lightrag/    # LightRAG 工作目录（gitignore）
│   ├── tests/
│   └── .env.example
├── frontend/             # 静态 SPA
├── scripts/              # start / run-backend / run-frontend / run-lightrag / stop
├── docs/examples/
└── docker-compose.yml    # Neo4j（可选）
```

## 快速开始

推荐一键启动（LightRAG + 后端 + 前端）：

```bash
./scripts/start.sh
# 停止：./scripts/stop.sh
```

统一入口：http://localhost:3000 （API：http://localhost:8000/api）

也可分别启动三个进程：

### 1. 后端

```bash
cd backend
# 推荐使用仓库根目录 .venv
source ../.venv/bin/activate   # 或 python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"

cp .env.example .env
# 也可稍后在前端「设置」页配置 LLM

../scripts/run-backend.sh
```

- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/api/health
- LightRAG 同源代理：http://localhost:8000/lightrag/...

### 2. 前端

```bash
./scripts/run-frontend.sh
```

浏览器打开 http://localhost:3000 。

### 3. LightRAG（知识库）

```bash
./scripts/run-lightrag.sh
```

工作目录：`backend/data/lightrag/`（含 `.env`、inputs、rag_storage）。  
图谱嵌入页：分类详情「知识图谱」tab → iframe `/lightrag/webui/index.html#/embed/graph?workspace=…`。

### 4. 一键停止

```bash
./scripts/stop.sh
```

## 功能入口

| 路由 | 说明 |
|------|------|
| `#simulate` | 新建推演 |
| `#kb` | **知识库**：上传/列表/删除文档（进入 LightRAG） |
| `#knowledge` | **知识图谱**：LightRAG WebUI 图谱嵌入 |
| `#settings` | **设置**：前端配置 LLM 模型与 API Key |

LLM 配置保存到 SQLite，并同步写入 `backend/data/lightrag/.env`；**改 key/model 后请重启 LightRAG**。

## API（节选）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/PUT | `/api/llm-settings` | 读写运行时 LLM 配置（key 仅回掩码） |
| GET | `/api/kb/status` | LightRAG 是否可达 |
| GET/POST | `/api/kb/documents` | 列表 / 上传 |
| DELETE | `/api/kb/documents/{id}` | 删除 |
| GET | `/api/simulations/...` | 推演相关（见 `/docs`） |

## 示例场景

见 [docs/examples/startup.txt](docs/examples/startup.txt)。

## 运行测试

```bash
cd backend
source ../.venv/bin/activate
pytest -v
```

## Neo4j（可选）

```bash
docker compose up -d
```

推演流水线仍可使用 Graphiti/builtin GraphRAG；前端图谱展示已切换为 LightRAG。

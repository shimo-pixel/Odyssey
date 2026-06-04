# PRDS - Parallel Reality Decision Simulator

多智能体平行世界决策推演系统。通过构建 N 个策略不同的智能体，在随机事件驱动的模拟环境中竞争推演，输出最可能成功的决策轨迹。

## 功能

- **10 阶段流水线**：本体建模 → 知识图谱 → 世界初始化 → 随机事件 → 多 Agent 决策循环 → 淘汰竞争 → 评分 → 轨迹 → 反事实分析 → 策略提炼
- **LLM 驱动决策**：每个 Agent 独立生成 Thought / Reasoning / Decision / Action
- **确定性结果层**：LLM 选择行动，规则引擎计算资源变更
- **FastAPI 服务**：异步后台模拟，进度查询，完整结果输出
- **Web UI**：访问 `/` 即可使用简易推演界面

## 快速开始

### 1. 安装依赖

```bash
cd /home/shimo/Odyssey
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .   # 将 prds 包安装到虚拟环境（推荐）
```

> 若 `pip install -e .` 因网络失败，可直接用 `./run.sh` 启动（自动设置 `PYTHONPATH=src`）。

### 2. 配置环境

```bash
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY（或使用 Mock 模式）
```

### 3. 启动服务

```bash
# 方式 A（推荐，需先 pip install -e .）
prds
# 或
uvicorn prds.main:app --reload --host 0.0.0.0 --port 8000

# 方式 B（无需 pip install -e .）
./run.sh
```

- API 文档：http://localhost:8000/docs
## 前端页面

基于 Stitch 设计稿（Lumina Precision 设计系统），包含 5 个页面：

| 路由 | 页面 | 功能 |
|------|------|------|
| `#simulate` | 模拟输入 | 填写背景/目标，启动推演 |
| `#monitor/{id}` | 实时监控 | 进度条、Agent 宇宙可视化、排行榜 |
| `#results/{id}` | 结果与策略 | 冠军轨迹、反事实、路线图 |
| `#agents` | 智能体实验室 | 10 种策略原型卡片 |
| `#knowledge/{id}` | 知识图谱 | 本体节点与关系可视化 |

访问 http://localhost:8000/ 即可使用。
- 健康检查：http://localhost:8000/health

### 4. 提交推演（Mock 模式，无需 API Key）

```bash
curl -X POST "http://localhost:8000/simulations?use_mock=true" \
  -H "Content-Type: application/json" \
  -d '{
    "current_state": {
      "background": "早期 SaaS 创业公司，5 人团队，现金 100 万",
      "resources": {"cash": 100, "team_size": 5, "users": 100, "revenue": 0},
      "constraints": ["18个月 runway"],
      "market_info": {"tam": 5000, "competition_intensity": 0.6},
      "risks": ["竞争激烈"],
      "opportunities": ["远程办公趋势"]
    },
    "goal": {
      "description": "12个月内营收100万，用户1万",
      "success_metrics": {"revenue": 100, "users": 10000}
    },
    "config": {"agent_count": 10, "periods": 6, "seed": 42}
  }'
```

### 5. 查询进度与结果

```bash
SIM_ID="<返回的 simulation_id>"

curl "http://localhost:8000/simulations/$SIM_ID"
curl "http://localhost:8000/simulations/$SIM_ID/result"
curl "http://localhost:8000/simulations/$SIM_ID/agents"
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/simulations?use_mock=false` | 提交场景，后台启动推演 |
| GET | `/simulations/{id}` | 运行状态与进度 |
| GET | `/simulations/{id}/result` | 完整推演结果 |
| GET | `/simulations/{id}/agents` | Top Agent 列表 |
| GET | `/health` | 健康检查 |

## 配置项

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `OPENAI_API_KEY` | - | LLM API 密钥 |
| `PRDS_LLM_MODEL` | gpt-4o-mini | Agent 决策模型 |
| `PRDS_LLM_MODEL_ANALYSIS` | gpt-4o | 反事实/策略提炼模型 |
| `PRDS_MAX_CONCURRENT_LLM` | 20 | LLM 并发上限 |
| `PRDS_DEFAULT_AGENT_COUNT` | 50 | 默认 Agent 数 |
| `PRDS_DEFAULT_PERIODS` | 120 | 默认模拟周期 |
| `PRDS_CHECKPOINT_INTERVAL` | 5 |  checkpoint 间隔 |

## 运行测试

```bash
pytest -v
```

## 项目结构

```
src/prds/
├── main.py              # FastAPI 入口
├── config.py            # 配置
├── models/domain.py     # 领域模型
├── ontology/            # 阶段1：本体与知识图谱
├── world/               # 阶段2-3：世界状态与事件
├── agents/              # 阶段4-5：Agent 工厂与运行时
├── simulation/          # 阶段5-6：行动、循环、编排
├── analysis/            # 阶段7-10：评分、轨迹、反事实、提炼
├── llm/                 # LLM 客户端
├── storage/             # SQLite 持久化
└── api/                 # REST 路由
```

## 成本控制建议

- 开发/测试：使用 `use_mock=true` 或 `agent_count=5, periods=3`
- 生产：`agent_count=50`, `periods=24~120`，淘汰 Agent 不再调用 LLM
- 分析阶段使用更贵的模型，批量决策使用便宜模型

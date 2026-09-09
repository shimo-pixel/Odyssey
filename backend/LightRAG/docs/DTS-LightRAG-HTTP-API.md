# LightRAG HTTP API 参考（DTS 集成版）

Base URL：`http://39.96.26.122:9621`

---

## 公共说明

### Workspace 请求头

业务接口需指定任务空间（与 DTS 任务名称一致，如「飞行员优选2」）：

| Header | 适用场景 |
|--------|----------|
| `LIGHTRAG-WORKSPACE: <name>` | 纯 ASCII 名称 |
| `LIGHTRAG-WORKSPACE-B64: <base64>` | 含中文等非 ASCII 名称 |

```bash
WS='飞行员优选2'
HDR="LIGHTRAG-WORKSPACE-B64: $(printf '%s' "$WS" | base64 -w0)"
```

---

## 1. SQLite 导入 / 添加 / 删除

路由前缀：`/sqlite`

### 1.1 列出可导入表

```http
GET /sqlite/tables?database_path=<SQLite文件路径>
```

```bash
curl -s 'http://39.96.26.122:9621/sqlite/tables?database_path=/path/to/military-task.db' \
  -H "$HDR"
```

**响应：**

```json
{
  "database_path": "/path/to/military-task.db",
  "tables": ["pilot", "military_unit"]
}
```

---

### 1.2 批量导入（异步）

将 SQLite 表读取后**逐行**经 LLM 转为自然语言（每行单独描述、保留全部字段），合并为一份文档并入队写入知识图谱。后台执行，适合多表导入。

> 行级并发由环境变量 `SQLITE_IMPORT_ROW_LLM_CONCURRENCY` 控制（默认 8）。LLM 失败时会对该行使用确定性字段叙述作为兜底。

```http
POST /sqlite/import
```

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `database_path` | string | 是 | SQLite 文件路径 |
| `tables` | string[] | 否 | 要导入的表；省略则导入全部用户表 |
| `max_rows_per_table` | int | 否 | 每表最大读取行数，默认 200，最大 5000 |
| `language` | string | 否 | 自然语言输出语言，默认 `Chinese` |
| `file_source_prefix` | string | 否 | 生成文档前缀，默认 `sqlite_import` |
| `resolve_cross_table_links` | bool | 否 | 是否解析跨表外键，默认 `true` |

```bash
curl -s -X POST 'http://39.96.26.122:9621/sqlite/import' \
  -H 'Content-Type: application/json' \
  -H "$HDR" \
  -d '{
    "database_path": "/path/to/military-task.db",
    "tables": ["pilot", "military_unit"],
    "max_rows_per_table": 1000,
    "language": "Chinese"
  }'
```

**响应：**

```json
{
  "status": "started",
  "message": "SQLite import started in background...",
  "job_id": "sqlite_job_xxx",
  "database_path": "/path/to/military-task.db",
  "tables": ["pilot", "military_unit"]
}
```

进度轮询：`GET /documents/pipeline_status` 或 `GET /documents/track_status/{track_id}`。

---

### 1.3 批量导入（同步）

与 `/sqlite/import` 相同逻辑，等待全部表转换并入队后返回。适合脚本调用，耗时可较长。

```http
POST /sqlite/import_sync
```

支持两种请求方式：

**方式 A — JSON（服务端本地路径，与旧版兼容）**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `database_path` | string | 是 | LightRAG 进程可访问的 SQLite 绝对路径 |
| `tables` | string[] | 否 | 要导入的表；省略则导入全部用户表 |
| `max_rows_per_table` | int | 否 | 每表最大读取行数，默认 200，最大 5000 |
| `language` | string | 否 | 自然语言输出语言，默认 `Chinese` |
| `file_source_prefix` | string | 否 | 默认 `sqlite_import` |
| `resolve_cross_table_links` | bool | 否 | 是否解析跨表外键，默认 `true` |

**方式 B — multipart/form-data（文件流上传，适合远程调用）**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | file | 是 | SQLite 数据库二进制流（`.db` / `.sqlite` / `.sqlite3`） |
| `tables` | string | 否 | 逗号分隔表名，或 JSON 数组字符串 `["pilot","team"]` |
| `max_rows_per_table` | int | 否 | 默认 200 |
| `language` | string | 否 | 默认 `Chinese` |
| `file_source_prefix` | string | 否 | 默认 `sqlite_import` |
| `resolve_cross_table_links` | bool | 否 | 默认 `true` |

上传文件会暂存到 `{working_dir}/sqlite_uploads/`，单文件大小上限由环境变量 `SQLITE_UPLOAD_MAX_BYTES` 控制（默认 100MB）。

```bash
# 远程上传 SQLite 文件
curl -s -X POST 'http://39.96.26.122:9621/sqlite/import_sync' \
  -H "$HDR" \
  -F 'file=@/path/to/task_2070332708185243649.db' \
  -F 'language=Chinese' \
  -F 'file_source_prefix=sqlite_task_2070332708185243649' \
  -F 'resolve_cross_table_links=true'
```

**响应：**

```json
{
  "status": "success",
  "message": "SQLite import finished: 2 queued, 0 skipped, 0 failed.",
  "database_path": "/path/to/military-task.db",
  "results": [
    {
      "table": "pilot",
      "file_source": "sqlite_import_pilot.txt",
      "track_id": "track_xxx",
      "row_count": 120,
      "text_chars": 8500,
      "status": "queued",
      "error": null
    }
  ]
}
```

---

### 1.4 添加单表

将 SQLite 中**单张新表**导入当前任务空间。

```http
POST /sqlite/table/upload
```

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_space_id` | string | 是 | 任务空间 ID，须与 `LIGHTRAG-WORKSPACE` 头一致 |
| `database_path` | string | 是 | SQLite 文件路径 |
| `table_name` | string | 二选一 | 物理表名 |
| `table_id` | string | 二选一 | 元数据表 ID（可在 `dts_meta_object` 等目录表解析） |
| `max_rows_per_table` | int | 否 | 默认 200 |
| `language` | string | 否 | 默认 `Chinese` |
| `replace_if_exists` | bool | 否 | 若该表已导入，先删后重新上传，默认 `false` |
| `file_source_prefix` | string | 否 | 文档前缀，省略时与历史导入一致 |

```bash
curl -s -X POST 'http://39.96.26.122:9621/sqlite/table/upload' \
  -H 'Content-Type: application/json' \
  -H "$HDR" \
  -d '{
    "task_space_id": "飞行员优选2",
    "database_path": "/path/to/military-task.db",
    "table_name": "pilot",
    "replace_if_exists": false
  }'
```

**响应：**

```json
{
  "status": "success",
  "message": "Table 'pilot' queued for indexing",
  "task_space_id": "飞行员优选2",
  "database_path": "/path/to/military-task.db",
  "table": "pilot",
  "file_source": "sqlite_military-task_pilot.txt",
  "track_id": "track_xxx",
  "row_count": 120,
  "text_chars": 8500,
  "error": null
}
```

---

### 1.5 删除单表

删除某张 SQLite 表在 LightRAG 中对应的文档、向量与知识图谱数据。

```http
POST /sqlite/table/delete
```

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_space_id` | string | 是 | 任务空间 ID，须与 `LIGHTRAG-WORKSPACE` 头一致 |
| `database_path` | string | 是 | SQLite 文件路径 |
| `table_name` | string | 二选一 | 物理表名 |
| `table_id` | string | 二选一 | 元数据表 ID |
| `delete_llm_cache` | bool | 否 | 是否同时清理 LLM 抽取缓存，默认 `false` |
| `file_source_prefix` | string | 否 | 文档前缀 |

```bash
curl -s -X POST 'http://39.96.26.122:9621/sqlite/table/delete' \
  -H 'Content-Type: application/json' \
  -H "$HDR" \
  -d '{
    "task_space_id": "飞行员优选2",
    "database_path": "/path/to/military-task.db",
    "table_name": "pilot"
  }'
```

**响应：**

```json
{
  "status": "success",
  "message": "Deleted document for table pilot",
  "task_space_id": "飞行员优选2",
  "database_path": "/path/to/military-task.db",
  "table": "pilot",
  "file_source": "sqlite_military-task_pilot.txt",
  "doc_id": "doc-xxx",
  "error": null
}
```

`status` 取值：`success` / `not_found` / `busy` / `failure`。流水线繁忙时返回 `busy`，需稍后重试。

---

## 2. Query 检索

三个接口共用同一请求体。

### 公共请求体

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | 是 | 检索问题，至少 3 个字符 |
| `mode` | string | 否 | `mix`（推荐）/ `local` / `global` / `hybrid` / `naive` / `bypass`，默认 `mix` |
| `hl_keywords` | string[] | 否 | 高级关键词 |
| `ll_keywords` | string[] | 否 | 低级关键词 |
| `top_k` | int | 否 | 检索实体/关系数量上限 |
| `include_references` | bool | 否 | 是否返回引用，默认 `true` |
| `stream` | bool | 否 | 是否流式（各 endpoint 有默认值） |
| `response_type` | string | 否 | 如 `Multiple Paragraphs` |

---

### 2.1 一次性 JSON 回答

```http
POST /query
```

```bash
curl -s -X POST 'http://39.96.26.122:9621/query' \
  -H 'Content-Type: application/json' \
  -H "$HDR" \
  -d '{
    "query": "飞行员训练评分标准是什么",
    "mode": "mix",
    "include_references": true
  }'
```

**响应：**

```json
{
  "response": "根据知识图谱，飞行员训练评分主要涉及……",
  "references": [
    { "reference_id": "1", "file_path": "/documents/train_eval.txt" }
  ]
}
```

---

### 2.2 流式 NDJSON 回答

```http
POST /query/stream
```

每行一个 JSON 对象，含 `response` 字段的块追加为答案文本；首块可能含 `references`。

```bash
curl -N -X POST 'http://39.96.26.122:9621/query/stream' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/x-ndjson' \
  -H "$HDR" \
  -d '{
    "query": "飞行员训练评分",
    "mode": "mix",
    "stream": true
  }'
```

**响应示例：**

```json
{"references":[{"reference_id":"1","file_path":"/documents/a.txt"}]}
{"response":"根据知识图谱，"}
{"response":"飞行员训练评分……"}
```

---

### 2.3 结构化检索数据

返回实体、关系等结构化数据，供图谱高亮使用。

```http
POST /query/data
```

```bash
curl -s -X POST 'http://39.96.26.122:9621/query/data' \
  -H 'Content-Type: application/json' \
  -H "$HDR" \
  -d '{
    "query": "飞行员训练评分",
    "mode": "mix"
  }'
```

**响应：**

```json
{
  "status": "success",
  "message": "Query executed successfully",
  "data": {
    "entities": [
      {
        "entity_name": "飞行员档案",
        "entity_type": "concept",
        "description": "……"
      }
    ],
    "relationships": [
      {
        "src_id": "飞行员档案",
        "tgt_id": "训练评分",
        "description": "……",
        "weight": 1.0
      }
    ],
    "chunks": [],
    "references": []
  },
  "metadata": { "mode": "mix" }
}
```

---

## 3. Web 图谱嵌入

### 3.1 嵌入 URL

在 iframe 中加载无 chrome 的知识图谱页面：

```
http://39.96.26.122:9621/webui/index.html#/embed/graph?workspace=<工作区>&lang=zh&hg=5
```

| 参数 | 说明 |
|------|------|
| `workspace` | 任务空间名称（URL 编码，如 `%E9%A3%9E%E8%A1%8C%E5%91%98%E4%BC%98%E9%80%892`） |
| `lang` | 界面语言，`zh` / `en` |
| `theme` | 外观主题，`light` / `dark`（与宿主应用同步） |
| `hg` | 图谱默认展开深度 |

也可在 iframe 就绪后通过 postMessage 切换主题（无需重载）：

```javascript
iframe.contentWindow.postMessage(
  { type: 'lightrag:set-theme', theme: 'dark' },
  'http://39.96.26.122:9621'
);
```

**HTML 示例：**

```html
<iframe
  src="http://39.96.26.122:9621/webui/index.html#/embed/graph?workspace=%E9%A3%9E%E8%A1%8C%E5%91%98%E4%BC%98%E9%80%892&lang=zh&theme=dark&hg=5"
  width="100%"
  height="600"
  style="border: none;"
></iframe>
```

---

### 3.2 搜索高亮（postMessage）

仅打开 embed URL **不会**自动高亮检索结果。父页面需：

1. 调用 `POST /query/data` 获取 `entities` / `relationships`
2. 等待 iframe 发出 `lightrag:graph-ready` 后，向 iframe 发送高亮消息

**高亮：**

```javascript
iframe.contentWindow.postMessage({
  type: 'lightrag:graph-search-highlight',
  payload: {
    entityNames: ['飞行员档案', '训练评分'],
    relationships: [{ source: '飞行员档案', target: '训练评分' }],
    focusEntityNames: ['飞行员档案']  // 可选，聚焦节点
  }
}, 'http://39.96.26.122:9621');
```

**清除高亮：**

```javascript
iframe.contentWindow.postMessage({
  type: 'lightrag:graph-clear-search-highlight'
}, 'http://39.96.26.122:9621');
```

**监听 iframe 就绪：**

```javascript
window.addEventListener('message', (e) => {
  if (e.origin !== 'http://39.96.26.122:9621') return;
  if (e.data?.type === 'lightrag:graph-ready') {
    // 发送高亮 payload
  }
});
```

---

### 3.3 典型流程

```
检索关键词
  ├─ POST /query/stream  → 展示 LLM 流式答案
  └─ POST /query/data      → 得到 entities + relationships
         └─ postMessage    → iframe 图谱高亮（数据追溯）
```

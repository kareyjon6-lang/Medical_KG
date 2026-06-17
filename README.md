# 中医知识图谱问答系统

这是一个面向中医方剂、药材、症状、功效与图谱证据的全栈问答系统。当前版本已经完成登录注册、管理员用户管理、流式问答、多历史对话任务隔离、方药检索、三维知识图谱浏览、本地实体抽取模型接入与 Neo4j/FAISS 图谱检索链路。

## 当前版本能力

- 典雅中药风格登录注册页，支持用户登录、用户注册、管理员登录。
- 普通用户进入智能问答、方药搜索、知识图谱页面。
- 管理员进入后台，可创建、删除普通用户或管理员账号。
- 管理员知识入库支持方药资料识别预览、正式导入与删除，并尽量避免普通操作触发全量向量重建。
- 问答页支持多个历史对话，每个历史对话拥有独立消息、推理轨迹、进度和任务状态。
- 同一历史对话再次提问会打断旧任务；不同历史对话可以并行运行不同问答任务。
- 模型回答完成后，左侧“问答”导航和历史对话项可显示未读提示。
- 推理轨迹按语义改写、实体抽取、图谱证据、回答生成展示，并支持 Cypher 中文片段横向拼接。
- 搜索页支持方剂、药材、功效、来源等条件检索。
- 图谱页支持实体关系浏览，并解释 `1跳/2跳` 图谱扩展深度。
- 后端启动时预热实体抽取模型、embedding 模型、FAISS index 和节点映射，减少首次问答等待。

## 技术栈

- 前端：Next.js、React、plain CSS、lucide-react、three、react-force-graph-3d
- 后端：FastAPI、Uvicorn、Pydantic
- 问答流程：LangGraph、LangChain
- 大模型：通过 `MODEL_BASE_URL`、`MODEL_NAME`、`MODEL_API_KEY` 配置兼容接口
- 实体抽取：本地微调 `bert-base-chinese` token classification 模型
- 图谱与检索：Neo4j、FAISS、sentence-transformers
- 存储：PostgreSQL，开发 smoke test 可使用 SQLite

## 目录结构

```text
medical_KG_project/
|-- web/                         # Next.js 前端
|-- __005__fastapi/              # FastAPI 后端
|-- __004__langgraph_more_nodes/ # LangGraph 中医问答节点
|-- __003__create_neo4j_database/# Neo4j 导入、元数据、FAISS 脚本
|-- common/                      # 配置、Neo4j、存储、LLM、实体抽取
|-- tests/                       # 后端与服务测试
|-- scripts/                     # 本地实体抽取模型训练脚本
|-- docker-compose.pg.yml
|-- DEPLOYMENT.md
`-- requirements.txt
```

历史采集、抽取、训练试验、设计稿与演示材料不属于当前发布主路径，部分目录仅作为参考保留。

## 环境变量

复制 `.env.example` 为 `.env`，按本地环境填写：

```text
MODEL_API_KEY=
MODEL_BASE_URL=
MODEL_NAME=

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=

DATABASE_URL=postgresql://medical_kg_user:medical_kg_pg_2026@localhost:15433/medical_kg
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
FRONTEND_ORIGINS=http://localhost:3010,http://127.0.0.1:3010

EMBEDDING_MODEL_PATH=
TCM_EXTRACTOR_MODEL_PATH=models/tcm_entity_extractor_best
TCM_EXTRACTOR_DEVICE=auto

TCM_ADMIN_USERNAME=admin
TCM_ADMIN_PASSWORD=admin123
```

如果只做本地快速验证，可以临时使用 SQLite：

```powershell
$env:DATABASE_URL="sqlite:///data/app_memory.sqlite3"
```

## 快速启动

### 1. 安装后端依赖

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

如果使用本机已有 Conda 环境，也可以直接使用项目环境，例如：

```powershell
D:\Anaconda\envs\KG\python.exe -m pip install -r requirements.txt
```

### 2. 启动 PostgreSQL

```powershell
docker compose -f docker-compose.pg.yml up -d
```

### 3. 启动 FastAPI 后端

```powershell
D:\Anaconda\envs\KG\python.exe -m uvicorn __005__fastapi.app.main:app --host 127.0.0.1 --port 8000
```

健康检查：

```text
http://localhost:8000/api/health
```

### 4. 启动前端

```powershell
cd web
npm install
npm run dev
```

访问：

```text
http://localhost:3010
```

## 主要接口

### 认证与用户

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/admin/login`
- `GET /api/auth/me`
- `POST /api/auth/logout`
- `GET /api/admin/users`
- `POST /api/admin/users`
- `DELETE /api/admin/users/{user_id}`

### 问答与历史对话

- `POST /process`
- `POST /api/chat/jobs`
- `GET /api/chat/jobs/{job_id}`
- `POST /api/chat/jobs/{job_id}/cancel`
- `GET /api/chat/threads`
- `POST /api/chat/threads`
- `GET /api/chat/threads/{thread_id}/messages`
- `DELETE /api/chat/threads/{thread_id}/messages`
- `DELETE /api/chat/threads/{thread_id}`

### 搜索与图谱

- `GET /api/search`
- `GET /api/graph`
- `GET /api/memory`

## 问答任务模型

当前版本使用三层标识避免多对话状态串扰：

- `session_id`：登录会话。
- `thread_id`：历史对话。
- `job_id`：一次具体提问任务。

同一个 `thread_id` 内只能有一个 active job，新问题会取消旧 job；不同 `thread_id` 的 job 可并行运行。前端按 thread 保存独立的 `messages`、`thoughts`、`progress`、`loading`、`unread` 和 `jobId`，切换页面或新增其他历史对话不会中断正在运行的问答任务。

## 实体抽取模型

当前运行时实体抽取使用本地微调模型，不再依赖通用大模型直接生成实体 JSON。

- 基座模型：`bert-base-chinese`
- 任务形式：`token classification`
- 正式模型目录：`models/tcm_entity_extractor_best`
- 训练入口：`scripts/train_tcm_entity_extractor.py`
- 运行时加载：`common/tcm_entity_extractor.py`

训练命令示例：

```powershell
D:\Anaconda\envs\Chapter3_RAG\python.exe scripts\train_tcm_entity_extractor.py --epochs 8 --early-stopping-patience 2 --batch-size 8 --output-dir models\tcm_entity_extractor_best --max-length 256
```

训练数据来自：

- `__002__extract_information/extract_formula_finetune_data.json`
- `__002__extract_information/extract_herb_finetune_data.json`

当前最佳训练摘要：

- 请求最大轮数：`8`
- `early stopping patience`：`2`
- 最佳轮数：`5`
- 最佳步数：`1185`
- 最佳验证集指标：`eval_entity_f1=0.9087`
- 实际提前停止于：`7` 轮

## 图谱与 FAISS

完整问答能力依赖 Neo4j 与 FAISS：

- Neo4j 存储方剂、药材、症状、疾病、功效、出处等实体与关系。
- FAISS 存储图谱节点名称向量，用于实体匹配。
- 后端启动时会尝试预热实体抽取模型、embedding 模型、FAISS index 和 `id2text` 节点映射。
- 若预热失败，后端会记录日志但不阻塞启动；相关问答或检索能力会在运行时体现错误。

## 验证命令

后端关键测试：

```powershell
D:\Anaconda\envs\KG\python.exe -m pytest tests/test_auth_service.py tests/test_pg_memory_store.py tests/test_fastapi_auth_routes.py tests/test_fastapi_services.py tests/test_train_tcm_entity_extractor.py tests/test_tcm_entity_extractor.py tests/test_extract_entity_node.py tests/test_generate_cypher_node.py -q
```

前端测试与构建：

```powershell
cd web
npm test
npm run build
```

语法检查：

```powershell
D:\Anaconda\envs\KG\python.exe -m py_compile __005__fastapi/app/main.py common/pg_memory_store.py common/tcm_entity_extractor.py
```

## 维护说明

- 不要提交 `.env`、本地数据库、日志、pid、模型目录、FAISS 索引和前端构建产物。
- 发布前至少运行一轮后端测试、前端测试和前端构建。
- PostgreSQL 是推荐运行存储；SQLite 仅用于本地 smoke test。
- 管理员默认账号优先读取 `TCM_ADMIN_USERNAME` / `TCM_ADMIN_PASSWORD`，未配置时本地默认 `admin/admin123`。
- 传统采集、训练和设计素材目录可能很大，默认不纳入发布提交。

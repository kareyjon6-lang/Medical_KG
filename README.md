# 中医知识图谱问答与共享缓存系统

这是一个面向中医方剂、药材、症状、功效与图谱证据的全栈问答系统。当前版本在原有 Neo4j + FAISS 图谱问答链路之上，新增了 `Redis + PostgreSQL` 共享问答缓存方案，用于沉淀高频问答、加速重复问题命中，并在缓存不可用时自动回退到知识图谱主链路。

README 主要用于快速说明系统能力、共享缓存架构、目录结构、环境变量和本地启动方式。

## 当前版本能力

- 典雅中药风格登录注册页，支持用户登录、用户注册、管理员登录。
- 普通用户进入智能问答、方药搜索、知识图谱页面。
- 管理员进入后台，可创建、删除普通用户或管理员账号。
- 管理员知识入库支持方药资料识别预览、正式导入与删除，并尽量避免普通操作触发全量向量重建。
- 新增 Redis + PostgreSQL 共享问答缓存：日常问候与高频问答可被跨用户复用。
- 支持精确命中、相似命中、Redis 热缓存回填与 PostgreSQL 持久化缓存。
- Redis 不可用时自动降级到 PostgreSQL 缓存；缓存整体失效时继续走 Neo4j + LangGraph 主问答链路。
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
- 存储：PostgreSQL 持久化业务数据与共享问答缓存、Redis 维护热缓存，开发 smoke test 可使用 SQLite

## 当前版本重点

- 共享问答缓存不再只依赖接口内的硬编码日常问候，而是统一写入 PostgreSQL 的 `qa_cache_entries`。
- Redis 仅承担热缓存与快速精确命中，键空间形如 `qa_cache:exact:{question_hash}`。
- PostgreSQL 负责缓存持久化、命中次数、过期时间和种子问答管理。
- 中等相似度问题会基于混合相似度分数筛选后，再由轻量模型做二次确认，避免误命中。
- 主链路生成的答案只有在满足质量门槛时才会进入共享缓存，降低缓存污染。

## Redis + PostgreSQL 共享问答缓存方案

当前问答链路按以下顺序工作：

1. 用户提问后，先做问题归一化与 `question_hash` 计算。
2. 优先查询 Redis 精确热缓存，命中后直接返回，并刷新 TTL。
3. Redis 未命中时，查询 PostgreSQL 精确缓存；命中后回填 Redis。
4. 精确缓存未命中时，从 PostgreSQL 候选缓存中做相似问题检索与二次确认。
5. 仍未命中时，进入 Neo4j + LangGraph 主链路生成新答案。
6. 新答案若满足质量规则，则写入 PostgreSQL，并尽量同步写入 Redis。

存储职责划分如下：

- `PostgreSQL`
  - 用户、会话、历史对话、后台操作记录
  - 共享问答缓存表 `qa_cache_entries`
  - 命中次数、过期时间、种子数据状态
- `Redis`
  - 高频问答精确命中热缓存
  - PostgreSQL 精确/相似命中后的回填结果
  - 较短 TTL 的热点答案加速

降级策略如下：

- Redis 缺失 Python 依赖、服务未启动、密码错误或连接失败时，不阻塞问答主链路。
- PostgreSQL 缓存可继续承担共享问答命中。
- 当两级缓存都未命中时，系统自动回退到知识图谱推理链路。

## 目录结构

```text
medical_KG_project/
|-- web/                         # Next.js 前端
|-- __005__fastapi/              # FastAPI 后端
|-- __004__langgraph_more_nodes/ # LangGraph 中医问答节点
|-- __003__create_neo4j_database/# Neo4j 导入、元数据、FAISS 脚本
|-- common/                      # 配置、Neo4j、存储、LLM、实体抽取、共享问答缓存
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
REDIS_PASSWORD=change-me-to-a-strong-local-password
REDIS_URL=redis://:change-me-to-a-strong-local-password@localhost:16379/0
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
FRONTEND_ORIGINS=http://localhost:3010,http://127.0.0.1:3010
LLM_API_CONCURRENCY=3

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

### 2. 配置 Redis 密码并启动 PostgreSQL + Redis

先在 `.env` 中设置 `REDIS_PASSWORD`，再启动容器：

```powershell
docker compose -f docker-compose.pg.yml up -d
```

默认容器说明：

- PostgreSQL：`localhost:15433`
- Redis：`127.0.0.1:16379`

如只想单独重建 Redis：

```powershell
docker compose -f docker-compose.pg.yml up -d --force-recreate medical-kg-redis
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

共享缓存相关行为由问答接口内置触发，当前不单独暴露缓存管理 API。

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

## 共享缓存规则

- 日常问候如“你好”“你是谁”“再见”会在启动时作为种子问答写入 PostgreSQL，并尽量同步进 Redis。
- 精确命中优先走 Redis，未命中再查 PostgreSQL。
- 相似命中基于字符相似度、token/bigram 覆盖率和 BM25 归一化分数综合判断。
- 中等相似度候选会通过轻量模型做 JSON 二次确认，避免把不同问题误判成同一答案。
- 主链路答案需要满足长度、完整性、无报错、无隐私泄露、非上下文依赖等规则，才允许入库。
- 热门普通问答命中次数达到阈值后会延长 PostgreSQL 过期时间；种子问答默认不过期。

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

## 存储结构说明

- PostgreSQL：关系型主存储，当前业务表包含 `users`、`user_sessions`、`chat_threads`、`chat_messages`、`chat_jobs`、`knowledge_import_jobs`、`user_memories`、`qa_cache_entries`。
- Redis：非关系型热缓存，没有传统“表”；本项目当前主要使用 `qa_cache:exact:{hash}` 这一类 key 前缀。
- Neo4j：存储方剂、药材、症状、疾病、功效、出处等图谱实体与关系。
- FAISS：存储图谱节点名称向量，用于实体匹配与检索召回。

## 验证命令

后端关键测试：

```powershell
D:\Anaconda\envs\KG\python.exe -m pytest tests/test_auth_service.py tests/test_pg_memory_store.py tests/test_qa_cache.py tests/test_async_llm_chain.py tests/test_fastapi_auth_routes.py tests/test_fastapi_services.py tests/test_train_tcm_entity_extractor.py tests/test_tcm_entity_extractor.py tests/test_extract_entity_node.py tests/test_generate_cypher_node.py -q
```

前端测试与构建：

```powershell
cd web
npm test
npm run build
```

语法检查：

```powershell
D:\Anaconda\envs\KG\python.exe -m py_compile __005__fastapi/app/main.py common/pg_memory_store.py common/qa_cache.py common/llm.py common/tcm_entity_extractor.py
```

## 维护说明

- 不要提交 `.env`、本地数据库、日志、pid、模型目录、FAISS 索引和前端构建产物。
- 发布前至少运行一轮后端测试、前端测试和前端构建。
- PostgreSQL 是推荐运行存储；SQLite 仅用于本地 smoke test。
- Redis 是共享问答缓存的热缓存层，建议始终通过 `.env` 配置强密码，不要沿用默认空密码或宿主机 6379 端口。
- 管理员默认账号优先读取 `TCM_ADMIN_USERNAME` / `TCM_ADMIN_PASSWORD`，未配置时本地默认 `admin/admin123`。
- 传统采集、训练和设计素材目录可能很大，默认不纳入发布提交。

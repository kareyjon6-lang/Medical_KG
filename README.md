# 中医药知识图谱问答系统

这是一个面向中医药问答、知识检索和图谱探索的全栈项目。发布版仓库聚焦当前可运行主线：`web/` 的 Next.js 前端、`__005__fastapi/` 的 FastAPI 后端、`__004__langgraph_more_nodes/` 的问答工作流，以及 `common/` 和 `__003__create_neo4j_database/` 中的运行时依赖与图谱索引资源。

为保证仓库简洁，这个 GitHub 发布版已经移除了采集、抽取、训练、旧演示和设计过程文件，只保留运行完整产品所需的代码与测试。

## 主要能力

- 用户注册、登录、会话校验和退出登录
- 问答页流式回复，支持思考过程展示和历史线程切换
- 方剂/中药搜索，支持分类、来源和功效过滤
- 3D 知识图谱浏览，支持 1 跳/2 跳扩展和关系筛选
- 管理员登录、用户创建与删除
- PostgreSQL/SQLite 兼容的用户、会话、聊天和长期记忆存储
- Neo4j + FAISS 的实体匹配与图谱查询

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | Next.js、React、plain CSS、lucide-react、react-force-graph-3d、three |
| 后端 | FastAPI、Uvicorn |
| 问答编排 | LangGraph、LangChain |
| 图谱与检索 | Neo4j、FAISS、Sentence Transformers |
| 业务存储 | PostgreSQL，开发/测试可使用 SQLite |

## 项目结构

```text
medical_KG_project/
├── web/                            # Next.js 主前端
├── __005__fastapi/                 # FastAPI 后端
├── __004__langgraph_more_nodes/    # LangGraph 问答工作流
├── __003__create_neo4j_database/   # 运行时图谱元数据与 FAISS 索引
├── common/                         # 公共配置、Neo4j、LLM、存储模块
├── tests/                          # Python 后端测试
├── docker-compose.pg.yml           # 本地 PostgreSQL compose 配置
├── DEPLOYMENT.md                   # 部署说明
└── requirements.txt                # Python 依赖
```

## 架构流程

```mermaid
flowchart LR
    User[用户] --> Web[Next.js 前端]
    Web --> API[FastAPI]
    API --> Store[PostgreSQL 或 SQLite]
    API --> Workflow[LangGraph 工作流]
    API --> Search[搜索服务]
    API --> Graph[图谱服务]
    Workflow --> FAISS[FAISS 实体匹配]
    Workflow --> Neo4j[Neo4j]
    Search --> Neo4j
    Graph --> Neo4j
```

## 环境要求

- Python 3.10+
- Node.js 18+，建议 20+
- Neo4j 5.x 或 Neo4j Aura
- PostgreSQL 14+，本地快速测试也可用 SQLite
- 可选：Docker

## 快速开始

### 1. 安装后端依赖

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，填入真实配置：

```text
MODEL_API_KEY=
MODEL_BASE_URL=
MODEL_NAME=
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=
DATABASE_URL=postgresql://medical_kg_user:medical_kg_pg_2026@localhost:15433/medical_kg
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
FRONTEND_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
EMBEDDING_MODEL_PATH=
```

### 3. 启动数据库

```powershell
docker compose -f docker-compose.pg.yml up -d
```

快速本地 smoke test 也可以直接改用 SQLite：

```powershell
$env:DATABASE_URL="sqlite:///data/app_memory.sqlite3"
```

### 4. 启动后端

```powershell
python -m uvicorn __005__fastapi.app.main:app --host 0.0.0.0 --port 8000
```

健康检查地址：`http://localhost:8000/api/health`

### 5. 启动前端

```powershell
cd web
npm install
npm run dev
```

打开 `http://localhost:3000`

## 核心接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| POST | `/api/auth/register` | 注册 |
| POST | `/api/auth/login` | 用户登录 |
| POST | `/api/auth/admin/login` | 管理员登录 |
| GET | `/api/auth/me` | 当前用户信息 |
| POST | `/api/auth/logout` | 退出登录 |
| POST | `/process` | 流式问答 |
| GET | `/api/chat/history` | 聊天历史 |
| GET | `/api/chat/threads` | 会话线程列表 |
| POST | `/api/chat/threads` | 创建会话线程 |
| GET | `/api/chat/threads/{thread_id}/messages` | 读取线程消息 |
| DELETE | `/api/chat/threads/{thread_id}/messages` | 清空线程消息 |
| DELETE | `/api/chat/threads/{thread_id}` | 删除线程 |
| GET | `/api/memory` | 长期记忆 |
| GET | `/api/search` | 方剂/中药搜索 |
| GET | `/api/graph` | 图谱查询 |
| GET | `/api/admin/users` | 管理员查看用户 |
| POST | `/api/admin/users` | 管理员创建用户 |
| DELETE | `/api/admin/users/{user_id}` | 管理员删除用户 |

## 测试与构建

后端：

```powershell
pytest tests/test_auth_service.py
pytest tests/test_pg_memory_store.py
pytest tests/test_fastapi_auth_routes.py
pytest tests/test_fastapi_services.py
```

前端：

```powershell
cd web
npm test
npm run build
```

## 运行时资源说明

`__003__create_neo4j_database/` 中保留了当前运行所需的图谱元数据和 FAISS 实体索引。要恢复完整问答和实体匹配能力，需要在本地或服务器准备：

- 可访问的 Neo4j 数据库
- 可用的向量模型路径 `EMBEDDING_MODEL_PATH`
- `.env` 中正确的模型、图数据库和前后端地址配置

## 维护建议

- 不要提交 `.env`、数据库文件、日志和前端构建产物
- 发布前至少跑一轮后端测试和前端构建
- 生产环境优先使用 PostgreSQL，SQLite 仅用于本地测试

# 中医药知识图谱问答系统

这是一个面向中医药知识检索、智能问答和知识图谱探索的全栈项目。本仓库内容对应本地的 `medical_KG_project` 项目文件夹。项目当前主前端是 `web/` 目录下的 Next.js 应用，后端是 FastAPI 服务，知识图谱使用 Neo4j，用户、会话、历史对话和长期记忆可使用 PostgreSQL 存储。`__006__streamlit/` 目录保留为早期/备用演示入口，不是当前主前端。

## 当前能力

- 用户登录、注册、会话校验和退出登录。
- 中医药问答页面，支持 `/process` 流式输出、模型思考过程展示、历史对话线程切换。
- 方药/中药搜索页面，支持分类筛选、最近搜索、热门检索和实体详情预览。
- 3D 知识图谱页面，支持以搜索实体为中心加载图谱、1 跳/2 跳关系扩展、关系过滤、节点详情查看。
- FastAPI 后端提供认证、问答、历史记录、记忆、搜索和图谱接口。
- PostgreSQL/SQLite 兼容的记忆存储，支持用户、会话、聊天线程、聊天消息和长期记忆。
- Neo4j + FAISS 支持实体匹配、图谱查询和相关节点扩展。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 主前端 | Next.js、React、plain CSS、lucide-react、react-force-graph-3d、three |
| 后端 API | FastAPI、Uvicorn |
| 问答编排 | LangGraph、LangChain |
| 图数据库 | Neo4j |
| 向量检索 | FAISS、Sentence Transformers |
| 业务存储 | PostgreSQL，开发/测试可使用 SQLite |
| 数据处理 | Python、Pandas、BeautifulSoup、Requests |
| 备用演示 | Streamlit，位于 `__006__streamlit/` |

## 项目结构

```text
medical_KG_project/
├── web/                            # 当前主前端：Next.js 应用
│   ├── app/                        # App Router 页面与全局样式
│   ├── components/                 # Workbench 等核心界面组件
│   ├── lib/                        # 前端 API helper
│   ├── public/images/              # 前端视觉资源
│   └── tests/                      # 前端接口与流式解析测试
├── __005__fastapi/                 # FastAPI 后端服务
│   └── app/main.py                 # 当前后端入口
├── common/                         # 公共配置、Neo4j、LLM、PG/SQLite 存储等模块
├── __004__langgraph_more_nodes/    # LangGraph 问答工作流与节点
├── __003__create_neo4j_database/   # Neo4j 导入、元数据导出、FAISS 索引脚本
├── __002__extract_information/     # 方药/中药结构化信息抽取脚本
├── __001__clawler/                 # 原始方药/中药爬取脚本与小型语料文件
├── __007__training/                # 本地抽取模型训练相关脚本
├── __006__streamlit/               # 历史 Streamlit 演示入口，非当前主前端
├── tests/                          # Python 后端与存储测试
├── docs/                           # 设计与实施文档
├── design/                         # 视觉设计说明
├── docker-compose.pg.yml           # 本地 PostgreSQL compose 配置
├── DEPLOYMENT.md                   # 部署说明
├── requirements.txt                # 后端运行依赖
└── requirements-training.txt       # 训练相关依赖
```

## 架构流程

```mermaid
flowchart LR
    User[用户] --> Web[Next.js 前端 web/]
    Web --> API[FastAPI 后端]
    API --> Auth[用户与会话存储 PostgreSQL/SQLite]
    API --> Workflow[LangGraph 问答工作流]
    API --> Search[搜索服务]
    API --> Graph[图谱服务]
    Workflow --> FAISS[FAISS 实体匹配]
    Workflow --> Neo4j[Neo4j 知识图谱]
    Search --> Neo4j
    Graph --> Neo4j
```

## 环境要求

- Python 3.10+
- Node.js 18+，建议 20+
- Neo4j 5.x 或 Neo4j Aura
- PostgreSQL 14+，本地快速测试也可以使用 SQLite
- 可选：Docker，用于启动本地 PostgreSQL

## 快速开始

### 1. 克隆项目

```bash
git clone git@gitee.com:ywj2230458284cvr/medical_-kg.git
cd medical_-kg
```

Gitee 克隆后的默认目录名是 `medical_-kg`；其内容就是本地 `medical_KG_project` 文件夹整理后的项目。

### 2. 配置 Python 环境

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 配置环境变量

复制 `.env.example` 为 `.env`，并填写真实配置。真实密钥不要提交到 Git。

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
```

### 4. 启动数据库

本地 PostgreSQL 可用 Docker 启动：

```powershell
docker compose -f docker-compose.pg.yml up -d
```

如果只是快速 smoke test，可临时使用 SQLite：

```powershell
$env:DATABASE_URL="sqlite:///data/app_memory.sqlite3"
```

Neo4j 需要单独启动，并保证 `.env` 中的 `NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD` 可用。

### 5. 启动后端

```powershell
python -m uvicorn __005__fastapi.app.main:app --host 0.0.0.0 --port 8000
```

后端健康检查：

```text
http://localhost:8000/api/health
```

### 6. 启动主前端

```powershell
cd web
npm install
npm run dev
```

打开：

```text
http://localhost:3000
```

## 常用接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 服务健康检查 |
| POST | `/api/auth/register` | 用户注册 |
| POST | `/api/auth/login` | 用户登录 |
| GET | `/api/auth/me` | 当前用户信息 |
| POST | `/api/auth/logout` | 退出登录 |
| POST | `/process` | 流式问答接口，支持 `thread_id` |
| GET | `/api/chat/history` | 当前用户历史消息 |
| GET | `/api/chat/threads` | 当前用户历史会话线程 |
| POST | `/api/chat/threads` | 创建历史会话线程 |
| GET | `/api/chat/threads/{thread_id}/messages` | 读取指定会话消息 |
| DELETE | `/api/chat/threads/{thread_id}` | 删除指定会话线程 |
| GET | `/api/memory` | 用户长期记忆 |
| GET | `/api/search` | 方药/中药检索 |
| GET | `/api/graph` | 知识图谱节点和关系 |

## 测试与构建

后端测试：

```powershell
pytest tests/test_pg_memory_store.py
pytest tests/test_fastapi_auth_routes.py
pytest tests/test_fastapi_services.py
```

前端测试与构建：

```powershell
cd web
npm test
npm run build
```

## 数据与生成产物说明

仓库已通过 `.gitignore` 排除以下本地生成内容：

- `.env`、本地密钥和私有配置。
- `.venv/`、`.venv-training/`、`node_modules/`、`.next/`。
- SQLite 数据库、运行日志、测试截图。
- 训练数据集、模型权重、FAISS/索引等大体积生成产物。

如需恢复完整图谱能力，需要在本地或服务器侧准备 Neo4j 数据、FAISS 索引和模型/Embedding 资源，并在 `.env` 中配置对应路径。

## Streamlit 说明

`__006__streamlit/` 是项目早期聊天演示入口，仍可用于调试旧流程：

```powershell
streamlit run __006__streamlit/__001__chat_app.py
```

但当前面向用户的主前端是 `web/` 目录下的 Next.js 应用，Gitee 项目说明、部署说明和后续开发均以 Next.js 前端为准。

## 贡献与维护

提交代码前建议执行后端测试和前端构建，确认没有把 `.env`、数据库、模型文件、截图和构建产物提交到仓库。

## 致谢

- Neo4j
- FastAPI
- LangGraph / LangChain
- Next.js / React
- FAISS
- Streamlit
- 中医百科等公开中医药资料来源

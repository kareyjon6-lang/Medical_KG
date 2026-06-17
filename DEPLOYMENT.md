# 部署说明

## 本次版本关注

- 后台知识入库支持方药资料识别、导入与删除链路整理。
- 问答页继续优化历史对话、流式反馈与展示细节。

## 服务组成

- 前端：将 `web/` 部署到 Vercel 或其他支持 Node.js 的平台
- 后端：将 `__005__fastapi/app/main.py` 部署到支持 Python 的平台，例如 Render、Railway、Fly.io 或云服务器
- 本地实体抽取模型：后端主机需要保留 `models/tcm_entity_extractor_best`
- 用户数据库：使用 PostgreSQL 存储用户、会话、聊天历史与长期记忆
- 图数据库：使用 Neo4j Aura 或自建 Neo4j
- 向量索引：保留当前 FAISS 文件，并在后端启动时加载

## 本地启动

### PostgreSQL

```powershell
docker compose -f docker-compose.pg.yml up -d
```

本地数据库参数：

```text
Host: localhost
Port: 15433
Database: medical_kg
User: medical_kg_user
Password: medical_kg_pg_2026
DATABASE_URL=postgresql://medical_kg_user:medical_kg_pg_2026@localhost:15433/medical_kg
```

### 后端

```powershell
python -m uvicorn __005__fastapi.app.main:app --host 0.0.0.0 --port 8000
```

### 前端

```powershell
cd web
npm install
npm run dev
```

### SQLite 快速验证

如果只做本地快速验证，可以使用：

```powershell
$env:DATABASE_URL="sqlite:///data/app_memory.sqlite3"
```

### 前端构建检查

```powershell
cd web
npm test
npm run build
npm audit --omit=dev
```

## 必要环境变量

以 `.env.example` 为模板，真实密钥与生产数据库密码应配置在部署平台中，不要提交到仓库。

运行时需要：

- `MODEL_API_KEY`
- `MODEL_BASE_URL`
- `MODEL_NAME`
- `NEO4J_URI`
- `NEO4J_USER`
- `NEO4J_PASSWORD`
- `DATABASE_URL`
- `NEXT_PUBLIC_API_BASE_URL`
- `FRONTEND_ORIGINS`
- `EMBEDDING_MODEL_PATH`
- `TCM_EXTRACTOR_MODEL_PATH`
- `TCM_EXTRACTOR_DEVICE`

其中：

- `TCM_EXTRACTOR_DEVICE=auto` 表示后端优先使用 CUDA，不可用时回退到 CPU

## 实体抽取模型训练

建议在带 CUDA 的环境中训练：

```powershell
D:\Anaconda\envs\Chapter3_RAG\python.exe scripts\train_tcm_entity_extractor.py --epochs 8 --early-stopping-patience 2 --batch-size 8 --output-dir models\tcm_entity_extractor_best --max-length 256
```

训练数据来源：

- `__002__extract_information/extract_formula_finetune_data.json`
- `__002__extract_information/extract_herb_finetune_data.json`

训练完成后，`models/tcm_entity_extractor_best` 下会生成：

- `model.safetensors`
- `tokenizer.json`
- `entity_lexicon.json`
- `eval_metrics.json`
- `training_summary.json`

## 安全检查

- 不要提交 `.env`
- 如果历史上有本地明文密钥泄露，发布前先轮换
- 生产环境使用 PostgreSQL，SQLite 只用于本地 `smoke test`
- Neo4j 对外查询场景尽量使用只读账号
- 生成式 Cypher 查询要放在只读保护下
- 不要在生产前端写死 `localhost`，应设置 `NEXT_PUBLIC_API_BASE_URL`
- `FRONTEND_ORIGINS` 应配置成你的线上前端域名，例如 `https://your-app.vercel.app`
- 已登录用户的 `user_id` 不应由前端直接传入，而应从认证信息中派生

## 最小联调流程

1. 启动 PostgreSQL，或将 `DATABASE_URL` 切到 SQLite
2. 启动 Neo4j
3. 启动 FastAPI
4. 启动前端 `web/`
5. 注册或登录
6. 搜索 `麻黄汤`
7. 打开图谱页，确认相关药材节点可见
8. 在问答页提问，确认聊天绑定的是当前登录用户
9. 提问 `银翘散可以治疗风热感冒吗？能不能加金银花？`，确认能抽出 `银翘散`、`风热感冒`、`金银花`

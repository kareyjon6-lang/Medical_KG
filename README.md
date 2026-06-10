# Medical KG Project

Medical KG Project is a slimmed-down full-stack release for traditional Chinese medicine question answering, knowledge search, and graph exploration. This GitHub-ready version keeps only the code and runtime assets required to run the product:

- `web/`: Next.js frontend
- `__005__fastapi/`: FastAPI backend
- `__004__langgraph_more_nodes/`: LangGraph QA workflow
- `common/`: shared config, storage, Neo4j, and model integration
- `__003__create_neo4j_database/`: runtime graph metadata and FAISS assets

Historical data collection, extraction, training, design, and demo-only materials were removed from Git tracking so the published repository stays focused and easier to maintain.

## Features

- User registration, login, session validation, and logout
- Admin login and user management
- Streaming medical QA with thread history
- Formula and herb search with filter support
- Interactive 3D knowledge graph exploration
- PostgreSQL or SQLite-backed chat and memory storage
- Neo4j and FAISS-backed entity matching and graph retrieval

## Tech Stack

- Frontend: Next.js, React, plain CSS, lucide-react, react-force-graph-3d, three
- Backend: FastAPI, Uvicorn
- Workflow: LangGraph, LangChain
- Retrieval: Neo4j, FAISS, sentence-transformers
- Storage: PostgreSQL, SQLite for local smoke tests

## Project Layout

```text
medical_KG_project/
|-- web/
|-- __005__fastapi/
|-- __004__langgraph_more_nodes/
|-- __003__create_neo4j_database/
|-- common/
|-- tests/
|-- docker-compose.pg.yml
|-- DEPLOYMENT.md
`-- requirements.txt
```

## Quick Start

### 1. Install Python dependencies

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and set the required values:

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

For a local smoke test without PostgreSQL:

```powershell
$env:DATABASE_URL="sqlite:///data/app_memory.sqlite3"
```

### 3. Start PostgreSQL

```powershell
docker compose -f docker-compose.pg.yml up -d
```

### 4. Start the FastAPI backend

```powershell
python -m uvicorn __005__fastapi.app.main:app --host 0.0.0.0 --port 8000
```

Health check:

```text
http://localhost:8000/api/health
```

### 5. Start the frontend

```powershell
cd web
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

## Key API Endpoints

- `GET /api/health`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/admin/login`
- `GET /api/auth/me`
- `POST /api/auth/logout`
- `POST /process`
- `GET /api/chat/history`
- `GET /api/chat/threads`
- `POST /api/chat/threads`
- `GET /api/chat/threads/{thread_id}/messages`
- `DELETE /api/chat/threads/{thread_id}/messages`
- `DELETE /api/chat/threads/{thread_id}`
- `GET /api/memory`
- `GET /api/search`
- `GET /api/graph`
- `GET /api/admin/users`
- `POST /api/admin/users`
- `DELETE /api/admin/users/{user_id}`

## Validation

Backend tests verified during cleanup:

```powershell
pytest tests/test_auth_service.py
pytest tests/test_pg_memory_store.py
pytest tests/test_fastapi_auth_routes.py
pytest tests/test_fastapi_services.py
```

Frontend checks verified during cleanup:

```powershell
cd web
npm test
npm run build
```

## Runtime Notes

The repository still includes the runtime graph metadata and FAISS assets under `__003__create_neo4j_database/`. To restore full QA and retrieval capability, you still need:

- An accessible Neo4j database
- A valid embedding model path in `EMBEDDING_MODEL_PATH`
- Correct model, database, and frontend/backend environment configuration

## Maintenance Notes

- Do not commit `.env`, local database files, logs, or frontend build output
- Run backend tests and a frontend build before publishing changes
- Prefer PostgreSQL in production and keep SQLite for local testing only

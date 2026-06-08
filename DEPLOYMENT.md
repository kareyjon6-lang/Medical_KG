# Deployment Notes

## Services

- Frontend: deploy `web/` to Vercel or another Node host.
- Backend: deploy `__005__fastapi/app/main.py` with Uvicorn/Gunicorn on Render, Railway, Fly.io, or a small cloud VM.
- Legacy Streamlit files remain for reference, but the deployable website entry is `web/`.
- User database: use PostgreSQL for users, sessions, chat history, and long-term memory.
- Graph database: use Neo4j Aura or a VM-hosted Neo4j instance.
- Vector index: keep the current FAISS entity-alignment files as backend artifacts; load them from persistent storage at startup.
- Local extractor: training is intentionally postponed; when the LoRA adapter is ready, mount it under `models/tcm_extractor_lora` and set `TCM_EXTRACTOR_ADAPTER_PATH`.

## Local Run

Project PostgreSQL:

```powershell
docker compose -f docker-compose.pg.yml up -d
```

Local Docker database settings:

```text
Host: localhost
Port: 15433
Database: medical_kg
User: medical_kg_user
Password: medical_kg_pg_2026
DATABASE_URL=postgresql://medical_kg_user:medical_kg_pg_2026@localhost:15433/medical_kg
```

Backend:

```powershell
python -m uvicorn __005__fastapi.app.main:app --host 0.0.0.0 --port 8000
```

Frontend:

```powershell
cd web
npm install
npm run dev
```

For quick local smoke tests without PostgreSQL, set:

```powershell
DATABASE_URL=sqlite:///data/app_memory.sqlite3
```

Production frontend build:

```powershell
cd web
npm test
npm run build
npm audit --omit=dev
```

## Required Environment Variables

Use `.env.example` as the template. Real API keys and database passwords must be configured in the deployment platform, not committed.

## Security Checklist

- Do not commit `.env`.
- Rotate any key that was previously exposed in a local project file before publishing the repository.
- Use PostgreSQL in production; SQLite is only for smoke tests.
- Use a read-only Neo4j user for public website queries when possible.
- Keep generated Cypher behind a read-only guard.
- Do not hardcode `localhost` in the production frontend; set `NEXT_PUBLIC_API_BASE_URL`.
- Set backend `FRONTEND_ORIGINS` to your deployed frontend domain, for example `https://your-app.vercel.app`.
- Do not accept `user_id` from the browser for authenticated chat; derive it from the bearer token.

## Minimum Local Smoke Flow

1. Start PostgreSQL or set `DATABASE_URL=sqlite:///data/app_memory.sqlite3`.
2. Start Neo4j.
3. Start FastAPI.
4. Start the Next.js frontend from `web/`.
5. Register or log in from the website.
6. Search for `麻黄汤`.
7. Open the graph view and verify related herbs render as nodes.
8. Ask the assistant a formula/herb question and verify the chat uses the authenticated user id.

# TCM Knowledge Graph Website Design

## Goal

Build a deployable portfolio-grade website for the existing TCM knowledge graph project. The site will keep the current LangGraph + FastAPI + FAISS + Neo4j reasoning chain, replace the API-based extraction step with a locally fine-tuned extraction model, and add a dynamic, polished Chinese medicine visual identity designed in Figma with HyperFrames-style motion direction.

## Scope

This work has two major deliverables:

1. A full web product based on Scheme 1:
   - Next.js frontend.
   - FastAPI backend.
   - Neo4j graph database.
   - Existing FAISS entity-alignment index for now.
   - Streamed AI assistant responses.
   - Search and graph visualization pages.
2. A local entity and relation extraction model:
   - Uses existing `extract_formula_finetune_data.json` and `extract_herb_finetune_data.json`.
   - Fine-tunes a small instruction model for structured JSON extraction.
   - Adds inference code that can replace the original API-based extraction flow used during data extraction.

## Current Evidence

The project already contains:

- LangGraph workflow in `__004__langgraph_more_nodes/langgraph_more_nodes.py`.
- Streamed FastAPI endpoint in `__005__fastapi/__001__fastapi.py`.
- Streamlit chat client in `__006__streamlit/__001__chat_app.py`.
- FAISS entity-alignment logic in `__004__langgraph_more_nodes/nodes/match_entity_from_neo4j_node.py`.
- Neo4j helpers in `common/neo4j_manager.py`.
- Fine-tuning data:
  - `__002__extract_information/extract_formula_finetune_data.json`: 671 samples.
  - `__002__extract_information/extract_herb_finetune_data.json`: 1433 samples.

Data audit:

- Total samples: 2104.
- Output format: JSON string with `entities` and `relations`.
- Entity types: `Disease`, `Herb`, `Symptom`, `Source`, `Effect`, `Formula`.
- Relation types: `TREATS_DISEASE`, `ALLEVIATES_SYMPTOM`, `HAS_INGREDIENT`, `FROM_SOURCE`, `HAS_EFFECT`, `HAS_SYMPTOM`.
- Some data cleanup is required: one `HAS_INGRED` typo and three blank relation labels were found.

## Product Design

### Pages

1. Assistant
   - Chat UI with streamed assistant answer.
   - Expandable reasoning panel showing semantic rewrite, entity matching, Cypher generation, and graph query results.
   - Medical safety note shown in a quiet persistent footer or side rail.

2. Search
   - Search formulas and herbs by exact name or fuzzy match.
   - Show core fields, aliases, effects, indications, dosage/usage, taboo, source, ingredients, symptoms, and diseases.
   - Include related entity chips that can be clicked to pivot the graph.

3. Graph Explorer
   - Force-directed graph for 1-hop and 2-hop neighborhoods.
   - Relation filters for ingredient, source, effect, disease, symptom.
   - Node detail drawer.
   - Search handoff from the Search page.

4. Project Architecture
   - Visual explanation of data ingestion, extraction, Neo4j import, FAISS alignment, LangGraph reasoning, and deployment.
   - Shows the model replacement story: API extractor -> local fine-tuned extractor.

### Visual Identity

Style direction: dynamic Chinese medicine / herbarium / knowledge graph.

Palette:

- Ink green: `#143D2B` for primary dark surfaces.
- Herb leaf: `#4E8F5A` for active states and graph highlights.
- Mineral cinnabar: `#B9472E` for warnings, important relation types, and key CTAs.
- Rice paper: `#F4EFE3` for backgrounds.
- Charcoal ink: `#1D2520` for primary text.
- Pale jade: `#C8D8B8` for secondary panels.

Typography:

- Chinese/UI body: use a readable Chinese system stack for production.
- Latin/data accents: serif + mono pairing in HyperFrames previews.
- Avoid generic AI-design defaults such as neon purple-blue gradients, large decorative bokeh, and dark slate-only palettes.

Motion:

- Background should feel alive but calm: subtle floating herb-line particles, graph-link pulses, and ink-brush reveal transitions.
- Chat streaming uses gentle token reveal and graph-node activation.
- Graph explorer uses physics movement only inside the visualization canvas; page layout itself remains stable.

Figma deliverable:

- Create or update a Figma design file containing:
  - Desktop Assistant screen.
  - Desktop Search + Graph screen.
  - Mobile Assistant screen.
  - Visual tokens page.
  - Motion notes based on HyperFrames style.

HyperFrames deliverable:

- Create a UI/motion concept composition or style prototype that demonstrates:
  - Herbarium background language.
  - Graph relation pulses.
  - Assistant answer reveal.
  - Page transition rhythm.

## Backend Design

The existing FastAPI file will be split into a production-oriented API package while preserving the old Streamlit path during migration.

New API endpoints:

- `GET /api/health`
- `POST /api/chat/stream`
- `GET /api/search?q=...`
- `GET /api/entities/{entity_name}`
- `GET /api/graph?name=...&depth=1`
- `POST /api/extract`

The chat endpoint will stream JSON lines or SSE events with stable event types:

- `rewrite`
- `intent`
- `entity_match`
- `cypher`
- `graph_result`
- `answer_delta`
- `done`
- `error`

Cypher safety:

- Only read-only queries are allowed.
- Reject `CREATE`, `MERGE`, `DELETE`, `SET`, `REMOVE`, `DROP`, `LOAD CSV`, and unrestricted `CALL`.
- Enforce `LIMIT` where practical.
- Use deterministic Cypher templates for Search and Graph Explorer instead of LLM-generated Cypher.

Session handling:

- Frontend generates an anonymous session id.
- Backend uses that id as LangGraph `thread_id`.
- No hardcoded `user_001`.

## Extraction Model Design

Recommended base model: `Qwen/Qwen2.5-1.5B-Instruct`.

Rationale:

- It is small enough for RTX 4060 Laptop 8GB with LoRA/QLoRA.
- It has strong Chinese instruction following.
- Its official model card highlights structured-output and JSON improvements.
- It supports long context up to the range needed by the current samples.

Training strategy:

- Supervised fine-tuning with LoRA.
- Input format follows chat messages:
  - system: strict TCM KG extractor with schema.
  - user: instruction + source text.
  - assistant: normalized JSON.
- Split train/eval with fixed seed.
- Save normalized data to `data/extraction/`.
- Save adapter to `models/tcm_extractor_lora/`.
- Keep a small validation report with:
  - JSON parse rate.
  - Entity type precision/recall approximation by exact set match.
  - Relation exact-match F1 approximation.
  - Invalid relation/type counts.

Code boundaries:

- `__007__training/prepare_extraction_dataset.py`: validates and normalizes current fine-tuning data.
- `__007__training/train_extractor_lora.py`: trains LoRA adapter.
- `__007__training/evaluate_extractor.py`: runs structural evaluation.
- `common/tcm_extractor_schema.py`: shared schema and normalization.
- `common/local_extractor.py`: inference wrapper.
- `__002__extract_information/__000__extract_graph_data_utils.py`: gains an option to use local extractor instead of API LLM.

The original API LLM can remain as a fallback, but local extraction becomes the preferred path when model artifacts exist.

## Frontend Design

The frontend will be created under `frontend/`.

Recommended stack:

- Next.js App Router.
- TypeScript.
- Tailwind CSS.
- Cytoscape.js or React Flow for graph visualization.
- Fetch streaming for chat.

Core frontend units:

- `app/assistant/page.tsx`
- `app/search/page.tsx`
- `app/graph/page.tsx`
- `app/architecture/page.tsx`
- `components/chat/`
- `components/graph/`
- `components/entity/`
- `lib/api.ts`
- `lib/session.ts`

## Deployment Design

Minimum deployable path:

- Frontend: Vercel.
- Backend: Render, Railway, Fly.io, or a small cloud VM.
- Neo4j: Neo4j Aura or a VM-hosted Neo4j.
- FAISS index: bundled with backend image or mounted as a read-only artifact.
- Model adapter: backend artifact path configured by environment variable.

Environment variables:

- `MODEL_API_KEY`
- `MODEL_BASE_URL`
- `MODEL_NAME`
- `NEO4J_URI`
- `NEO4J_USER`
- `NEO4J_PASSWORD`
- `EMBEDDING_MODEL_PATH`
- `TCM_EXTRACTOR_BASE_MODEL`
- `TCM_EXTRACTOR_ADAPTER_PATH`
- `NEXT_PUBLIC_API_BASE_URL`

## Testing And Verification

Backend:

- Unit tests for Cypher safety.
- Unit tests for schema normalization.
- Unit tests for search/graph response shape with mocked Neo4j client.
- Streaming endpoint smoke test.

Training:

- Dataset preparation verifies all outputs parse as JSON.
- Evaluation reports JSON parse rate and relation/entity metrics.
- Inference smoke test against one herb and one formula sample.

Frontend:

- Build must pass.
- Basic Playwright/browser smoke checks for Assistant, Search, and Graph pages.
- Visual check that mobile and desktop layouts do not overlap.

Figma/HyperFrames:

- Figma screens created and screenshot verified.
- HyperFrames prototype lint/validate/inspect pass if a composition is authored.

## Acceptance Criteria

The goal is complete only when:

1. The website has the four planned pages implemented.
2. Assistant chat streams responses from FastAPI.
3. Search returns entity details from Neo4j.
4. Graph Explorer renders related nodes and relationships.
5. Figma contains the designed screens and visual tokens.
6. HyperFrames visual/motion direction exists or is represented in the Figma motion notes.
7. A local fine-tuned extraction model or adapter has been trained.
8. Extraction inference can produce valid JSON for at least representative herb and formula examples.
9. Existing extraction code can use the local model path instead of the API LLM.
10. Security and deployment basics are addressed: no hardcoded localhost in production frontend, no fixed `user_001`, no committed secrets, and read-only Cypher safety.

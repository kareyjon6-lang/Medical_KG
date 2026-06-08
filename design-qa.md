# 设计验收

最终结果：通过。

## 范围

- 按用户提供的图 1-9 做高保真收敛：左侧窄墨绿侧栏、大号“药图”书法字、米纸底纹、朱砂按钮、书法标题、搜索筛选勾选样式、结果列表行距、右侧实体详情、深色三维图谱。
- 保留三个页面与既有功能：问答、搜索、图谱。
- 搜索页不嵌入图谱，只同步当前焦点并跳转图谱页。

## 本轮修正

- 2026-06-07 追加修正：
  - 图谱节点姓名牌文本统一为黑色，去掉方剂节点白字。
  - 搜索框改为固定网格：图标区、输入区、检索按钮同高对齐，检索按钮宽度固定为 164px。
  - 搜索页比例调整，右侧实体详情属性区改为内部滚动，“在问答中追问”按钮完整保留在首屏底部。
  - 问答核心节点恢复为 `medical_KG_project_original` 对应实现；当前 `__004__langgraph_more_nodes` 下 10 个问答链路文件与原始项目一致。
  - `/process` 使用对话 `thread_id` 作为 LangGraph 线程，避免不同历史对话串上下文。
  - 对纯寒暄增加快速路径，`你好` 返回原版同风格问候，实测约 49ms。
- 新增 `web/app/fidelity-final.css` 并在 `layout.jsx` 中最后导入，避免旧 CSS 重复覆盖导致设计图细节失效。
- 图 1：侧栏品牌改为大号“药图”与红色小印，隐藏工作台名和用户名，导航卡片尺寸与图示接近。
- 图 2：顶部右侧“清空对话 / 深色模式 / 登录已恢复”按钮组不可见；登录恢复仅保留轻量状态。
- 图 3：历史对话保留标题、数量、新建和删除；长期记忆区域隐藏。
- 图 4：实体类别仅保留“全部 / 方剂 / 药材”；来源出处和功效统一为勾选样式，无右侧数字。
- 图 5-8：搜索详情区加高并保留“在问答中追问”；移除“热词与最近搜索”；热门搜索“换一换”可轮换；移除“相关度 / 视图”；结果行距加大，避免横线压字。
- 图 9：三维图谱节点名直接显示在球体前方的米色姓名牌上，标签加大，画布居中。
- 搜索服务修复：类型筛选同时兼容 Neo4j 标签和节点属性 `label`，使“搜索到图谱”一致。

## 证据

- `web/ui-check-assistant-final.png`
- `web/ui-check-search-final.png`
- `web/ui-check-graph-final.png`
- `web/ui-verify-search-fixed.png`
- `web/ui-verify-graph-latest.png`

## 验证

- `cd web && npm test` 通过：7 项。
- `cd web && npm run build` 通过。
- `PYTHONPATH=D:\Desktop\new_project\medical_KG_project D:\Anaconda\envs\KG\python.exe -m pytest tests\test_fastapi_services.py tests\test_pg_memory_store.py tests\test_fastapi_auth_routes.py` 通过：22 项。
- 接口快验通过：`/api/search?q=一气散&label=Formula,Herb` 返回 1 条；`/api/graph?q=一气散` 返回 2 个节点，二者焦点一致。
- Playwright 截图验收通过：
  - 顶部 action 按钮组不可见。
  - 侧栏“药图”字号为 46px。
  - 图谱 canvas 存在，图谱场景尺寸约 1074x740。
  - 搜索页可显示“一气散”结果和实体详情。
- 本轮追加验证：
  - `cd web && npm test` 通过：7 项。
  - `cd web && npm run build` 通过。
  - `PYTHONPATH=D:\Desktop\new_project\medical_KG_project D:\Anaconda\envs\KG\python.exe -m pytest tests\test_fastapi_auth_routes.py tests\test_fastapi_services.py tests\test_pg_memory_store.py` 通过：23 项。
  - 真实 HTTP `/process` 输入 `你好`：49ms 返回，内容为“您好，请问您有什么中医相关的问题需要咨询？”。
  - 原版 8001 与新版 8000 对比 `麻黄汤的组成是什么？`：二者均走完整图谱链路，思考过程一致，答案均为麻黄、桂枝、杏仁、炙甘草。
  - 搜索页 DOM 验证：搜索框 80px，检索按钮 78px（外框 1px 边框差），视觉同高；“在问答中追问”按钮 rect bottom=763，小于 768px 视口高，完整可见。
## 2026-06-07 Final Follow-up QA

final result: passed

- Search page at 1422x768/100% uses columns `224px 638px 344px`, has no horizontal overflow, and keeps the "在问答中追问" action visible.
- Search detail now has a `detail-expand` dropdown for long "关联信息" content.
- Graph page no longer renders the "适配" and "重置" buttons; depth selection remains.
- Assistant streaming survives navigation away from `/assistant`; after completion on `/search`, the sidebar "问答" tab receives `has-unread`, and it clears after returning.
- Reasoning Cypher renders as one continuous line in the thinking panel, not token-per-line fragments.
- Direct graph QA for "麻黄汤的组成是什么？" now returns in about 1.8-2.5s with graph-backed answer: "杏仁、麻黄、桂枝、炙甘草".

Verification artifacts:

- `web/qa-final-search.png`
- `web/qa-final-graph.png`
- `web/qa-cross-page-debug.json`
- `web/qa-direct-answer-debug.json`

## 2026-06-07 100% Viewport Density QA

final result: passed

- Search page was rebalanced for normal browser 100% zoom. At 1422x768 and 1728x921, there is no horizontal or vertical page overflow, the right detail card remains inside the viewport, and the bottom "在问答中追问" action is fully visible.
- Search page density was reduced through tighter columns, smaller controls, denser filters, and a scroll-safe detail body so the page no longer relies on users zooming to 90%.
- Graph page grid rows were corrected so the toolbar height and scene/inspector heights match the real layout. At 1422x768 and 1728x921, the graph inspector stays inside the viewport, "用法" is visible, and both bottom actions are fully visible.
- Graph page was verified with real data on `http://localhost:3000/graph?q=麻黄汤`: 33 nodes, 37 relationships, WebGL canvas present, React hydration active, and relation filter interaction working.
- Added `web/next.config.mjs` with `devIndicators: false` so the local Next.js dev indicator no longer covers the lower-right action buttons after the dev server is restarted.

Verification artifacts:

- `web/qa-final-search-1422.png`
- `web/qa-final-graph-1422.png`
- `web/qa-density-final-search-1728.png`
- `web/qa-density-final-graph-1728.png`

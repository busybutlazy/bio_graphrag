# Code Review Report

> 日期：2026-07-08
> 審查基準 commit：b6def96（`git rev-parse --short HEAD` 的結果）
> 分支：main
> 審查範圍：`backend/app/`、`ingestion/pipeline/`、`frontend/`（後端 API、混合檢索管線、資料匯入管線、靜態展示前端）
> 審查模式：全局掃描
> 前次報告：無

## 摘要

- 審查檔案數：約 40（新審查：40，沿用前次：0）
- CRITICAL：0
- HIGH：2（已修復 2）
- MEDIUM：4（已修復 3，緩解 1）
- LOW：6（已修復 4，維持現狀 2）
- 已修復（本次）：9

> 修復進度（2026-07-08,基準 commit 未變,尚未 commit）：兩項 HIGH 與其餘安全/邏輯問題皆已修復。/admin 認證依使用者選擇採「具名多金鑰」。效能項依使用者選擇採「asyncpg 連線池 + 將同步 Neo4j 呼叫以 `anyio.to_thread` 卸載到 threadpool」,並一併把 async 路徑中的同步 OpenAI 呼叫也卸載。無法在此環境跑完整整合測試(三個 DB 未啟動、且 `backend/tests/conftest.py` 的 session 級 autouse fixture 需連 Postgres);已用臨時 venv 驗證:全模組 import、pyflakes 無警告;injection 白名單/payload 驗證/gateway 離線 fallback/eval mode/BFS 重構為純邏輯單元檢查全數通過;auth 以 TestClient 驗證(401 早於 DB、正確金鑰通過、valid key + 非法 type → 422);純邏輯 ingestion 測試 7 passed。

整體而言程式碼結構清晰、分層明確，approved-graph 邊界在檢索路徑上有一致地以 `status = 'approved'` 過濾。主要風險集中在兩點：curation 審核路徑對 Neo4j label 的字串插補造成 Cypher injection，以及 `/admin` 變更端點完全沒有認證。兩者相加使得「未經驗證即可注入 Cypher」在目前程式碼中是可達的，但考量本專案定位為 localhost demo、且記憶中已記錄「實體 DB 隔離延後處理」的決策，此處以 HIGH 標示並於建議中說明。

## 安全性發現

- [x] **[HIGH]** curation 審核路徑對 node/edge type 做字串插補，造成 Cypher injection
  - **修復**：`create_item` 加入 `_validate_curation_payload`,用 `normalize_concepts` 的 `VALID_NODE_TYPES`/`VALID_RELATIONSHIP_TYPES` 白名單驗證 type、並要求 `payload.id`,非法值回 422（route 已攔截 `CurationError`）。另在 sink 端 `load_neo4j._safe_type` 加上識別符正規表達式防護,確保任何路徑到達 Cypher label 插補前都經過檢查。
  - **位置**：`ingestion/pipeline/load_neo4j.py:11-33`（`write_nodes` / `write_edges`），觸發鏈路 `backend/app/curation/service.py:104-108`（`approve_item`）
  - **描述**：`write_nodes` 以 f-string 將 `node['type']` 直接插入 `MERGE (n:{node['type']} {{id: $id}})`，`write_edges` 同樣插入 `edge['type']`。這些 payload 來自 `curation_items` 資料表，而 `POST /admin/curation/items`（`routes_curation.py:24-27`）接受任意 `payload: dict`（`CurationItemCreate.payload`），建立時**完全沒有做 type 白名單驗證**（`create_item` 只是原封不動存入）。核准時 `approve_item` 直接把 payload 交給 `write_nodes([payload])`。攻擊者可送出 `type` 為 `Concept) DETACH DELETE n //` 之類的字串，在核准當下注入並執行任意 Cypher（刪除全圖、竄改節點等）。相對地，匯入管線路徑（`normalize_concepts.validate_nodes`）有 `VALID_NODE_TYPES` 白名單，但 curation 路徑繞過了它。
  - **建議**：在 `create_item`（或 `approve_item` 寫入前）以 `normalize_concepts.VALID_NODE_TYPES` / `VALID_RELATIONSHIP_TYPES` 驗證 `type`，非白名單值直接拒絕（422）。label 是保留字識別符，無法參數化，因此白名單驗證是必要防線；亦可對 `write_nodes`/`write_edges` 內的 label 加上 `re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', type)` 的硬性檢查作為第二道防護。

- [x] **[HIGH]** `/admin` curation 與 graph 變更端點沒有任何認證／授權
  - **修復**：依使用者選擇採「具名多金鑰」。新增 `app/api/auth.py`(`require_admin` dependency + `parse_api_keys`),以 env `ADMIN_API_KEYS`(`vendor:key` 逗號清單)驗 `X-API-Key` header 並辨識廠商;掛在 `routes_curation` 與 `routes_eval` 的 `/admin` router 上。未設金鑰時放行(demo/測試維持可跑),對外部署需設定。前端 `api` helper 由 `localStorage.adminApiKey` 帶 header;README 補上說明,並註明每廠商額度/期限刻意留為未來工作。已用 TestClient 驗證:設金鑰後缺/錯 header → 401(在 DB 呼叫前),正確金鑰 → 通過。
  - **位置**：`backend/app/api/routes_curation.py:12`（`prefix="/admin"`）、`backend/app/api/routes_eval.py:6`
  - **描述**：核准/拒絕 curation、合併節點、刪除節點、刪除邊等具破壞性的圖譜變更操作，以及 `create_curation_item`，皆掛在 `/admin` 之下卻沒有任何 auth dependency。任何能連到 API 的人都能刪除或竄改整個知識圖譜。目前唯一的存取控制是參數長度限制（見 `schemas/query.py` 註解），對變更端點不構成保護。此為記憶中「捨棄 visibility 欄位、之後改用實體 DB 隔離」決策的已知缺口，但在部署到非隔離環境前必須補上。
  - **建議**：至少為 `/admin` router 加上一個共用的 API-key / bearer token dependency（可先用環境變數比對）。長期則依原計畫以實體隔離或反向代理層的認證處理。若短期內確定僅綁 localhost，也應在 README／部署說明中明確標註此限制。

## 邏輯正確性發現

- [x] **[MEDIUM]** curation payload 建立時未做 schema 驗證，破壞下游資料完整性且是 injection 的前提
  - **修復**：與上述 HIGH #1 同一處 `_validate_curation_payload`,建立時即驗證 item_type/id/type,非法回 422。
  - **位置**：`backend/app/curation/service.py:75-90`（`create_item`）
  - **描述**：`create_item` 直接把任意 `payload` 存入 `curation_items`，不像 `load_postgres.stage_extraction_output`（LLM 產出路徑）會先呼叫 `validate_extraction.validate_extraction_output` 做 JSON schema 驗證。因此人工建立路徑可寫入缺欄位或型別非法的節點/邊，核准時才在 `write_nodes` 因 `node['type']`／`node['label']` 之類的 `KeyError` 或非法 Cypher 而失敗（500），且此為上述 Cypher injection 的入口。
  - **建議**：讓 `create_item` 走與 `stage_extraction_output` 相同的 `validate_extraction_output`（或至少驗證必要欄位 + type 白名單），把驗證前移到寫入 DB 前。

- [x] **[MEDIUM]** `merge_nodes` 對不存在的來源/目標節點仍回報成功
  - **修復**：`_merge_nodes_in_neo4j` 開頭先查兩節點是否存在,缺任一即丟 `CurationError(404)`;`merge_nodes_endpoint` 也補上 `CurationError` 攔截。
  - **位置**：`backend/app/curation/service.py:154-189`
  - **描述**：`_merge_nodes_in_neo4j` 的所有 Cypher 在來源或目標 id 不存在時只是 match 不到、不報錯，接著 `merge_nodes` 仍寫入一筆 `action='merge'` 的變更日誌並回傳 `{"status": "merged"}`。呼叫端無從得知合併其實沒發生，稽核日誌也會出現假的合併紀錄。相較之下 `delete_node`/`delete_edge` 都有 not-found 檢查並丟 `CurationError(404)`。
  - **建議**：在合併前先確認兩節點存在（例如 `RETURN count(*)`），缺任一則丟 `CurationError(404)`；`routes_curation.py:47-49` 的 `merge_nodes_endpoint` 也應像其他端點一樣攔截 `CurationError`。

- [x] **[LOW]** `create_item` / `stage_extraction_output` 對 `payload['id']` 缺失無防護
  - **修復**：`create_item` 路徑由 `_validate_curation_payload` 檢查 `payload.id`,缺失回 422。（`stage_extraction_output` 走 JSON schema 驗證,維持原樣。）
  - **位置**：`backend/app/curation/service.py:77`、`ingestion/pipeline/load_postgres.py:87,96`
  - **描述**：`item_id = f"curation:{payload['id']}"` 在 payload 無 `id` 欄位時丟未捕捉的 `KeyError`，對外呈現為 500 而非 422。
  - **建議**：驗證 `id` 存在（併入上面的 schema 驗證即可），缺失時回 422。

- [x] **[LOW]** OpenAI 回應內容可能為 None 時直接 `.strip()`
  - **修復**：`_openai_answer` 對 `content` 做 falsy 檢查並回退提示訊息;`_openai_check` 的 `json.loads` 包 try/except 並容忍 `content=None`。
  - **位置**：`backend/app/llm/gateway.py:52`（`_openai_answer`）、`gateway.py:113`（`_openai_check` 的 `json.loads`）
  - **描述**：`response.choices[0].message.content.strip()` 在模型回傳 `content=None`（如觸發 content filter）時丟 `AttributeError`；`_openai_check` 的 `json.loads(...content)` 在非法 JSON 時丟 `JSONDecodeError`，兩者皆會冒泡成 500。
  - **建議**：對 `content` 做 None 檢查與 fallback；`json.loads` 包 try/except，解析失敗時回退為「無法判定」的結果。

- [x] **[LOW]** eval 的 `mode` 判定與實際檢索路徑不一致
  - **修復**：`runner` 的 mode 改為同時檢查 `llm_provider == "openai"` 與 key,與 retriever/gateway 一致。
  - **位置**：`backend/app/eval/runner.py:90`
  - **描述**：報告的 `mode` 用 `"openai" if settings.openai_api_key else "offline"`，但 `retriever_vector._semantic_enabled` / `gateway._use_openai` 另外要求 `llm_provider == "openai"`。若設了 api_key 但 provider 非 openai，報告會標成 `openai`，實際管線卻走 offline，量測數據會被誤讀。
  - **建議**：抽出共用的 `_semantic_enabled()`（同時檢查 provider 與 key），runner 與 retriever/gateway 共用同一判定。

## 效能發現

- [x] **[MEDIUM]** 同步 Neo4j 呼叫在 async 端點內執行，會阻塞事件迴圈
  - **修復**：`library`、`concept_map`、`pipeline.retrieve`、curation 服務(approve/merge/delete)中的同步 Neo4j 呼叫改用 `anyio.to_thread.run_sync` 卸載到 threadpool;同時把 async 路徑中的同步 OpenAI 呼叫(`generate_answer`/`check_misconception`)一併卸載,避免網路 I/O 阻塞事件迴圈。`get_node`/`get_neighbors` 為同步 `def` 端點(FastAPI 本就丟 threadpool),維持原樣。
  - **位置**：`backend/app/api/routes_library.py:37`（`library` 為 `async def`，內部呼叫同步的 `fetch_nodes_brief`/`graph_counts`）、`routes_nodes.py:34`（`concept_map` async 呼叫同步 `expand_from_seeds`）、`curation/service.py` 全部 async 函式內的 `driver.session()` 同步操作
  - **描述**：`neo4j_driver.get_driver()` 回傳同步 Driver，其 `session().run()` 為阻塞 I/O。放在 `def`（sync）端點時 FastAPI 會丟到 threadpool 尚可；但放在 `async def` 端點/服務函式內會直接卡住事件迴圈，並行請求下延遲會被放大。`get_node`/`get_neighbors` 是 sync `def` 反而沒問題，`concept_map`/`library`/curation 服務則是 async 卻做同步 I/O。
  - **建議**：統一策略——要嘛改用 `neo4j.AsyncGraphDatabase`（如 `neo4j_client.py` 已在用）搭配 async session，要嘛把同步 Neo4j 工作用 `anyio.to_thread.run_sync` / `run_in_executor` 卸載到 threadpool。

- [x] **[MEDIUM]** 每次 DB 操作都新建 asyncpg 連線，沒有連線池
  - **修復**：新增 `app/db/pool.py`(以事件迴圈為鍵的惰性建立連線池,`min_size=1/max_size=10`),`chunks`、`query_logs`、curation 服務、`eval.runner._persist` 全改用 `async with connection()`;`main.py` 加 lifespan 於關閉時釋放連線池(建立仍為惰性,故啟動不需 Postgres 先就緒)。health check 的探測連線維持獨立。
  - **位置**：`backend/app/curation/service.py:19-25`、`db/chunks.py:8-14`、`db/query_logs.py:13`、`eval/runner.py:112`
  - **描述**：每個 request 對 Postgres 都 `asyncpg.connect(...)` 開新連線用完即關，沒有 pool。單次請求若多次查詢（如 `library` 對每個 topic 各開一次）連線開銷更明顯。
  - **建議**：以 `asyncpg.create_pool` 建立應用層連線池（FastAPI lifespan 啟動時建立、關閉時釋放），各 DB 函式改從 pool `acquire`。

- [~] **[MEDIUM]** `library` 端點對 topic 呈 N+1 查詢（已緩解，未收斂查詢結構）
  - **緩解**：連線池已消除每次查詢的連線開銷、Neo4j 查詢也卸載到 threadpool,4 個 topic 下影響已可忽略。依使用者選擇未進一步把每 topic 一次的查詢收斂成單一 SQL/Cypher;若 topic 數成長再處理。
  - **位置**：`backend/app/api/routes_library.py:39-50`
  - **描述**：迴圈中對每個 topic 各發一次 Postgres 查詢（`concept_ids_by_topic`）與一次 Neo4j 查詢（`fetch_nodes_brief`），再加上 `all_topics` 與 `graph_counts`，隨 topic 數線性成長且每次都新開連線。目前 sample 只有 4 個 topic 影響小，但屬明確的 N+1 型態。
  - **建議**：一次撈出所有 topic→concept_ids 的對應（單一 SQL group by），Neo4j 端也用單一 `n.id IN $ids` 查詢後在應用層分組。

- [ ] **[LOW]** `lexical_search` 每次全表掃描並重算 bigram
  - **位置**：`backend/app/db/chunks.py:73-100`
  - **描述**：離線 fallback 每次查詢載入所有 chunks 並即時計算 bigram 集合。程式碼註解已說明「corpus 很小所以可接受」，此處僅記錄為已知取捨。
  - **建議**：維持現狀即可；若語料成長，改用 Postgres 全文檢索或 `pg_trgm` 索引。

## 可維護性發現

- [x] **[LOW]** 提交進版控的預設密碼 `change_me`
  - **修復**：依使用者選擇保留佔位符讓 demo 可直接跑,在 `config.py` 與 `run.py` 加註解明確標示「僅供本地 demo,任何對外部署須以環境變數覆寫」。
  - **位置**：`backend/app/core/config.py:14,19`、`ingestion/pipeline/run.py:31,45`
  - **描述**：Postgres/Neo4j 密碼預設值 `change_me` 寫死於原始碼。雖為可被 `.env` 覆寫的佔位符，但若部署時忘記覆寫即成為弱憑證。
  - **建議**：對必要憑證不給預設值（缺少即啟動失敗），或在 README 明確要求覆寫；避免讓「能跑起來」的預設同時是弱密碼。

- [x] **[LOW]** `expand_from_seeds` 與 `fetch_neighbors` 的 BFS 邏輯幾乎重複
  - **修復**：抽出共用的 `_bfs_expand(session, seed_ids, depth, limit, nodes)`,兩個入口薄封裝;`fetch_neighbors` 內重複的展開查詢改用共用的 `_EXPAND_QUERY` 常數。已用 fake session 驗證 depth/limit/seed 語意與原本一致。
  - **位置**：`backend/app/graph/cypher_templates.py:71-183`
  - **描述**：兩個函式的 frontier BFS、edges/nodes 累積、node_limit 判斷幾乎相同，僅中心節點處理與回傳結構不同，`_EXPAND_QUERY` 也在 `fetch_neighbors` 內被重寫了一次。
  - **建議**：抽出共用的 BFS helper（吃 driver、初始 frontier、depth、limit，回傳 nodes/edges），兩個端點在其上薄封裝。

## 建議行動

1.（HIGH）在 curation 建立/核准路徑加入 type 白名單與 schema 驗證，堵住 `load_neo4j` 的 Cypher label injection——這是安全性最優先項，且順帶解掉 `create_item` 的 500 問題。
2.（HIGH）為 `/admin` router 加上最基本的認證（API key / bearer），或在部署文件明確標註「僅限隔離環境」的前提。
3.（MEDIUM）統一 Neo4j 存取模型（全 async 或一律卸載到 threadpool），並導入 asyncpg 連線池，一併改善 `library` 的 N+1。
4.（MEDIUM）補上 `merge_nodes` 的 not-found 檢查與端點層 `CurationError` 攔截。
5.（LOW）修 OpenAI 回應的 None/JSON 解析防護、eval 的 mode 判定一致性、預設密碼、BFS 重複碼。

## 審查範圍限制

- 未執行程式（無法連線 Postgres/Neo4j/Qdrant），所有發現以靜態閱讀為準，未做動態驗證或實際發送 injection payload 佐證。
- 未審查測試檔（`backend/tests/`、`ingestion/tests/`）的覆蓋充分性，僅確認其存在。
- 未審查 `design_handoff_honzo/` 的靜態 HTML 設計稿與 `frontend/styles.css`（純樣式，無邏輯）。
- 未評估相依套件版本的已知 CVE（未檢視 lock file / 版本鎖定情形）。
- `frontend/app.js` 僅就 XSS 相關的 `innerHTML` 用法做重點檢視：唯一的 `html:` 注入點（`app.js:519`）餵入的是後端 eval 的數值欄位，非使用者輸入，風險低；answer/feedback/snippet 皆以 `text:` 或 `title` 屬性渲染，無 XSS。

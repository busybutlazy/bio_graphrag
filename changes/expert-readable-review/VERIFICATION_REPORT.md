# Verification Report: expert-readable-review

- Plan revision: r1 (Approved) · Automation mode: supervised-auto · Risk: medium
- Scope verified: auto-approved tasks **T1–T8** (Part 1 前端 polish + Part 2 Phase B 後端). Phase C (T9–T11) not started (gated behind CP2/CP3).
- Environment: local Docker Compose (postgres/neo4j/qdrant/backend/nginx all running). Backend image rebuilt to bake new test files. Data dir live-mounted (`./data:/app/data`).
- Mode: evidence-only — no implementation edits during verification.

## Requirement → implementation → test

| AC | Requirement | Implementation | Evidence |
|----|-------------|----------------|----------|
| 1 | 卡片主視覺無 raw id/schema code/NODE·EDGE 代碼 | `loadQueue` head = 類型 pill + 名稱 / 關係句;技術細節移入 `<details>` | `frontend/app.js` (renderCuration); `node --check` OK — **手動視覺待 CP1** |
| 2 | edge 以節點名稱呈現,解析失敗退回 shortId 不報錯 | `resolveNodeLabels`: 佇列同儕 → `GET /nodes/{id}` → shortId,`try/catch` 靜默 | `frontend/app.js`; contract `GET /nodes/{id}` 回 label(§api_contract:71) — **手動視覺待 CP1** |
| 3 | 技術細節可展開,工程師資訊零遺失 | `<details class="q-tech">` 內含 id/action/原始關係/schema 明細 | `frontend/app.js`, `frontend/styles.css` — **手動視覺待 CP1** |
| 4 | 表單中文標籤、無 mono CODE、下拉中文但 value 為英文 code | `field(label,input,hint)`、`paintForm` zh option text + English `value` | `frontend/app.js` — **手動視覺待 CP1** |
| 5 | 批准/拒絕行為與 payload 不變 | `decide()` 與 submit body 未改動 | diff 檢視:兩函式未變更 |
| 6 | offline 可運作 | 前端純靜態;renderer 為 deterministic 純函式(無 LLM) | back_translation 無外部呼叫 |
| 7 | renderer P1–P5 白話句正確,Case5=gap | `back_translation.render_understanding` | `test_back_translation.py` 6 passed;gold 逐字比對 |
| 8 | engineer_gate Case1–4=pass, Case5=needs_schema_extension | `engineer_gate.evaluate` 複用既有驗證器 | `test_engineer_gate.py` 5 passed |
| 9 | gold 最小斷言逐案綠燈 | `gold/*.json` + `test_gold_examples.py` | 6 passed |
| 10 | backlog 含 Case5 + D6;policy 有白話⇄code 表 | `schema_gap_backlog.json` (5), `docs/schema-gap-policy.md` | JSON valid;文件含對照表 |

## Commands and results

| Command | Result |
|---|---|
| `node --check frontend/app.js` | OK (host static check;無前端容器 entrypoint) |
| CSS brace balance (awk) | 210/210 |
| host renderer 對 gold 逐字比對 | 5/5 ALL MATCH |
| `docker compose run --rm --build backend pytest tests/unit/test_back_translation.py tests/unit/test_engineer_gate.py tests/gold/test_gold_examples.py` | 初次 16 passed / 1 failed(gold case_002 資料錯) |
| (修正 gold 後) `docker compose run --rm backend pytest tests/gold/test_gold_examples.py` | 6 passed |
| `make test`(全套回歸) | **122 passed, 1 failed** (231.72s) |

新增測試合計 **17 passed**(back_translation 6 + engineer_gate 5 + gold 6)。

## Full-suite failure — pre-existing, unrelated to this change

- **Failing test**: `ingestion/tests/test_pipeline.py::test_pipeline_run_is_idempotent`
- **Symptom**: `assert chunk_count == len(chunks)` → `12 == 9` False.
- **Root cause**: `chunks` 表含 8 × `chunk:sample:*` + 4 × `doc:private:endocrine_demo_v1:chunk:*`。後 4 筆由既有的**文件抽取(extract)測試**寫入,並留存在共用的 Postgres volume(extract 路徑「chunks 立即寫入」為 documented 行為)。該測試以**全表列數**對比 9 筆 sample 來源,任何非乾淨 volume 都會失敗。
- **Attribution — 非本變更所致**:
  - seed loader 讀固定檔名(`biology_sample_{concepts,edges,documents,chunks}.json`),`data/sample/expert_demo/*` 對它不可見。
  - 本變更 diff = 前端 + `app/graph` 兩個純模組 + 新測試 + expert_demo 資料 + docs,**未新增任何 chunk、未觸及 ingestion pipeline 或該失敗測試**。
  - 證據:上文 chunk_id 列表(4 筆 private chunk 來自 extract 測試);`git diff` 範圍與 approved path scope 完全一致。
- **處置**:依 supervised-auto 契約,**未修改該失敗測試**(不在 approved path scope),記錄後停止。

## Mocks / skips / uncertainty

- 前端(T1–T4)無自動化測試框架 → 只做 `node --check` 靜態檢查 + 邏輯審視;**真正的視覺/互動驗收需人在跑起來的 app 上做(CP1)**。此為 known limitation,非本次可自動證明。
- `.env` 讀取被權限阻擋(secret);Postgres 查詢改用容器內 `$POSTGRES_USER`/`$POSTGRES_DB`,未接觸明文憑證。

## Conclusion

- 所有 change-scoped 檢查通過;新增 17 測試全綠。
- 全套 `make test` 唯一失敗為 **pre-existing、環境/volume-state 相關、與本變更無因果**的測試隔離問題。
- 未達「full verification 全綠」→ 依契約記錄並停止,交由人類決定(不代為修改越界測試、不繼續 Phase C)。

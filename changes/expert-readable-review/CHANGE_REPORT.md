# Change Report: expert-readable-review

- Plan revision: r1 (Approved) · mode: supervised-auto · risk: medium
- Scope executed: **all tasks T1–T11** (Part 1 前端 polish + Phase B 引擎 + Phase C 端點/UI/文件).
  Phase C (T9–T11) authorized to proceed by user instruction「先繼續」(covering CP2/CP3).
- Commit/push: **none** (deferred; out of scope).

## Completed

**Part 1 — 審訂頁面改成專家可讀**
- 中文 label 對照(11 node types / 13 relations),value/API 仍送英文 code。
- 待審卡片白話化:節點=類型pill+名稱+說明;關係=名稱—中文關係→名稱(edge id 解析:佇列同儕→`GET /nodes/{id}`→shortId,靜默 fallback)。
- 原始 id/schema/action → 可展開「技術細節」;schema 未過時卡片加警示。
- 表單人性化(中文欄位、去 mono code、白話 placeholder、下拉中文/value 英文)。批准/拒絕 API 與 payload 未變。

**Part 2 — Phase B 引擎**
- `back_translation.py`(純函式 P1–P5,無 LLM)+ `engineer_gate.py`(複用 `validate_extraction_output` + 型別白名單)+ 5 gold + 回歸測試 + `schema_gap_backlog.json` + `docs/schema-gap-policy.md`。

**Part 3 — Phase C 端點/UI/文件**
- `GET /admin/expert-demo/cases`(唯讀,admin key;`system_understanding`/`engineer_gate` 當場算不落地)+ main 掛載 + `api_contract.md`。
- 前端 `renderExpertDemo` 三 tab(AI提案 / 工程師gate / 專家審閱-強制隔離)+ 概念圖(複用 forceLayout;僅 label 無 id)+ sessionStorage。
- 文件:workflow、rule-card-format、3 張 rule cards、extraction_guidelines/README 索引。

## Observable behavior

- 前端「審訂」「審閱」分頁(`http://localhost:8080/app/`,`?v=20260722-3`)。
- `GET /admin/expert-demo/cases` → 200,5 案,gate 1–4 `pass` / 5 `needs_schema_extension`,白話理解句正確(live-verified via nginx)。
- 全程 offline 可跑(back_translation deterministic,零 token)。

## Contract / schema / migration impact

- **API 合約新增**:`GET /admin/expert-demo/cases`(read-only)。已補 `docs/api_contract.md`。
- DB schema / 圖型別:**無變更**。新型別只記 backlog。無 migration、無依賴新增。
- 不變式維持:expert-demo 端點不寫圖、不繞 curation、不碰 `status='approved'` 檢索。

## Tests

- 新增 **19** 測試全綠:`test_expert_demo.py`(2)、`test_back_translation.py`(6)、`test_engineer_gate.py`(5)、`test_gold_examples.py`(6)。
- `make test`(全套):**124 passed, 1 failed**。

## Not fully green — one pre-existing, unrelated failure

- `ingestion/tests/test_pipeline.py::test_pipeline_run_is_idempotent`:`chunk_count 12 != 9`。
- 原因:`chunks` 表殘留 4 筆 `doc:private:endocrine_demo_v1:chunk:*`(既有文件抽取測試寫入、留在共用 Postgres volume);該測試以全表列數比 9 筆 sample 來源。
- **非本變更所致**:seed loader 讀固定檔名,`expert_demo/*` 對它不可見;本 diff 不新增 chunk、不觸 ingestion pipeline。Phase C 前後此失敗完全相同(122→124 passed 皆同一失敗)。未修改該越界測試。

## Limitations / remaining work

- 前端(Part 1 卡片 + Part 3 三 tab)**無自動化測試**;需人在跑起來的 app 上做視覺/互動驗收(CP1/CP3)。
- 專家審查選擇僅存 sessionStorage(demo 範圍,不寫 DB — 符合 MVP 邊界)。
- 未提交任何 commit;由人類決定後續。

## Rollback

- 皆附加式,無 migration。回滾 = 還原 `frontend/{app.js,styles.css,index.html}`、刪 `backend/app/graph/{back_translation,engineer_gate}.py`、`backend/app/api/routes_expert_demo.py`、移除 `main.py` 內該 import + `include_router` 行、刪新測試/資料/docs;後端其餘路由不受影響。

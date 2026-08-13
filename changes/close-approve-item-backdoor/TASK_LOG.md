# Task Log: close-approve-item-backdoor

- **Plan revision**: 1
- **Approval evidence**: `IMPLEMENTATION_PLAN.md`〈Human Decisions and Approval〉—— jett / 2026-08-13,
  對 D1–D4 逐項批准(D1 含 `reject_item` 一併退場、D2 同意契約縮減、D3 supervised-auto、
  D4 不跑 `make eval`)。
- **Risk level**: medium
- **Automation mode**: supervised-auto
- **Auto-approved tasks**: T1、T2、T3、T4
- **Approved path scope**:
  `backend/app/api/routes_curation.py`、`backend/app/curation/service.py`、
  `backend/app/schemas/curation.py`、`backend/tests/integration/test_curation.py`、
  `docs/api_contract.md`、`CLAUDE.md`、`docs/notes.md`、
  `changes/close-approve-item-backdoor/`
- **Baseline Git state**:
  - 起點 `main` @ `8112fda`(PR #21 merge commit),工作區僅一個未追蹤項:
    `changes/close-approve-item-backdoor/`(本變更產出物)。無不明修改。
  - 執行分支:`feat/close-approve-item-backdoor`(**未 commit、未 push**)。
- **Baseline tests**(在 `8112fda` 實測,非引用其他分支的數字):
  ```
  docker compose build backend                                                   # exit 0
  docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q
  → 1 failed, 242 passed in 78.83s                                               # exit 1
  ```
  唯一失敗:`ingestion/tests/test_pipeline.py::test_pipeline_run_is_idempotent`
  (`assert 12 == 9`),volume 非乾淨造成的既有 flake,**非本變更造成**。
- **預期終值**:242 − 2(移除的測試)+ 1(新增的後門守衛)= **241**。
  若對不上必須具名說明。

---

## T1 — 移除單項寫入路徑

- **Boundary and allowed paths**:`backend/app/api/routes_curation.py`、
  `backend/app/curation/service.py`、`backend/app/schemas/curation.py`
- **Files changed**:
  - `routes_curation.py` —— 移除 `create_curation_item`、`approve_curation_item`、
    `reject_curation_item` 三個路由與 `CurationItemCreate` / `ApproveRejectRequest` 的 import;
    新增模組 docstring 說明**這條路徑是刻意不存在**,以及進入圖譜只剩群組端點一個入口。
  - `service.py` —— 移除 `create_item`(原 :119-135)與 `approve_item` / `reject_item`
    (原 :247-311,共 67 行);兩處各留一段註解說明移除的理由,避免日後被當成漏做而補回。
  - `schemas/curation.py` —— 移除 `CurationItemCreate`。
  - **保留(已逐一確認仍被使用)**:`GET /curation/items`、`list_items`、
    `CurationItemResponse`、`ApproveRejectRequest`(`routes_review.py:15`)、
    `_validate_curation_payload`(`create_group` 的 :169/:171)、
    `HTTPException`(graph 端點仍用)。
- **Container commands and exit codes**:
  ```
  grep -rn "approve_item\|reject_item\|create_item\|CurationItemCreate" backend/app/
  → 僅命中新寫的說明性註解,無程式碼參照
  docker compose build backend                                                     # exit 0
  docker compose run --rm -e OPENAI_API_KEY= backend pytest \
      tests/integration/test_review_groups.py tests/api/test_curation_groups.py -q
  → 36 passed in 43.74s                                                            # exit 0
  ```
- **Acceptance criteria demonstrated**:AC5(群組路徑**一行未改**且全數通過,
  這是「移除範圍沒有溢出」的直接證據)、AC7 的一半。
- **Tests not run and why**:全套留到 T4。
- **Deviations**:None
- **Result**: **Pass**

## T2 — 測試改寫與後門守衛

- **Boundary and allowed paths**:`backend/tests/integration/test_curation.py`
- **Files changed**:同上一檔。
- **Tests added/modified**:
  - `test_proposed_node_not_written_until_reviewed` → 改寫為
    **`test_proposed_statement_reaches_the_graph_only_after_approval`**:
    以 `POST /admin/curation/groups` 提案 → Neo4j 查無 → `POST /admin/review/groups/{id}/approve`
    → 查得到且 `status='approved'`。比原測試更強(原本只驗前半)。
  - **移除** `test_approve_writes_to_neo4j_and_logs_change` 與
    `test_reject_never_writes_to_neo4j_and_logs_change`。理由寫進測試檔註解:
    群組等價覆蓋已存在於 `test_review_groups.py::test_approve_group_writes_all_and_audits`
    與 `::test_reject_group_writes_nothing_and_audits`,重寫只是複製而非增加覆蓋。
  - **新增** `test_the_single_item_write_path_is_gone`:對三個被移除的路徑各發一次 POST,
    斷言 `status_code in (404, 405)`,並斷言 `GET` 仍回 200。
- **Container commands and exit codes**:
  ```
  docker compose build backend                                                     # exit 0
  docker compose run --rm -e OPENAI_API_KEY= backend pytest tests/integration/test_curation.py -q
  → 4 passed in 12.93s                                                             # exit 0
  ```
- **Acceptance criteria demonstrated**:AC1–AC4(測試層)、AC6。
- **Deviations**:None。`_fetch_change_log` 已確認仍被其餘兩個測試使用,未產生死碼。
- **Result**: **Pass**

## T3 — 文件同步

- **Boundary and allowed paths**:`docs/api_contract.md`、`CLAUDE.md`、`docs/notes.md`
- **Files changed**:
  - `api_contract.md` —— 刪除三個寫入端點的章節;在 `GET` 之後補一段說明
    **移除的理由是治理而非簡化**,並點出兩個缺口如何串成平行路徑。
  - `CLAUDE.md` —— 治理流程敘述由 `create_item`/`approve_item` 改寫為
    `create_group`/`approve_group`;白名單驗證時機由 *create* 改稱 *propose*(語意不變);
    新增一段「群組是審閱單位,沒有單項寫入路徑」,含**再加回去就要把守衛一起加回來**的警告。
  - `docs/notes.md` N7 —— 標明後門已關且**比原記載更寬**,並明寫
    **N7 不能因此視為完成**(部分處置仍需 grill)。
- **Container commands and exit codes**:不適用(純文件)。
- **Acceptance criteria demonstrated**:AC8。
- **Deviations**:None
- **Result**: **Pass**

## T4 — 完整驗證

- **Boundary**:無程式碼改動(evidence-only)。
- **Result**: **Pass** —— 詳見 `VERIFICATION_REPORT.md`。

---

## T5 — 審查發現處置(plan rev 2)

- **觸發**:`REVIEW_REPORT.md`(2026-08-13,獨立 session)。**Blocking 無**;High 1(H1)、
  Medium 1(M1)、Low 3、Suggestion 2。
- **人類處置決定**:jett,2026-08-13 —— 「全部修,升 rev 2」。
  H1 需要動 `README.md` 與 `docs/graph_plan.md`,在 rev 1 的批准路徑之外
  → **material change,plan 升 revision 2 並重新記錄批准**(rev 1 的批准就此失效)。
- **Boundary and allowed paths**:rev 2 的清單(新增 `README.md`、`docs/graph_plan.md`)。

### 五項發現,我逐項獨立驗證後全部成立

- **M1(Medium)—— 我寫了一個假的守衛。** 審查者是對的,而且這是本輪最該認的一項:
  被移除的 `approve_item` 在 item 不存在時**本來就 `raise CurationError(404, ...)`**
  (`git show HEAD:backend/app/curation/service.py` 第 250-251 行逐字確認)。
  所以 `assert status_code in (404, 405)` 對 approve/reject 兩條路徑**在端點存在與不存在的
  兩種世界裡結果相同**——同義反覆。而那個測試的 docstring 我還寫了
  「Anyone re-adding these routes has to make this test fail first」,**對三條中的兩條是假的**。
  這與我上一個變更被審查抓到的 N-2 是同一種失效,換個地方又犯一次。
  **改法**:改為斷言**路由表**(`{(route.path, method) for route in app.routes ...}`)不含
  `(path, "POST")`,鑑別力不再依賴狀態碼。
  **正向對照**(證明新斷言不是另一個同義反覆):
  ```
  docker compose run --rm -e OPENAI_API_KEY= backend python -c "...app.routes..."
  → POST /admin/curation/groups
    GET  /admin/curation/items
    GET items present  : True
    POST items present : False
  ```
  `GET` 在集合中,證明路徑字串格式的假設正確,負向斷言因此有意義。
- **H1(High)—— `README.md` 仍教讀者呼叫已移除的端點。** 實測 `README.md:115-125` 確有那兩條
  curl,且上一行寫「New nodes/edges go through human curation first」——
  **這句話正是本變更要推翻的**:那條路徑不但不存在了,它當初根本沒過任何 gate。
  `docs/graph_plan.md:362-364` 的 API 表亦同。
  **根因是 Plan 自己的掃描面沒做完**:〈In Scope〉憑印象列了三份文件,沒有做一次全域 grep。
  **改法**:README 兩條 curl 改為群組路徑並改寫上下文敘述;
  `graph_plan.md` §5.2 **就地標注刪除線與取代端點,並加一段更新說明**,
  不刪除原表(它是階段計畫書,改寫會失去歷史記錄價值)。
  **並補做審查者建議的全域 grep**:
  `grep -rn "curation/items" --include=*.{md,py,js,html,yml,sh} .`
  → 排除 `changes/` 與 `docs/codereview_report/` 後,剩餘命中全部是正確描述「已移除」的段落。
- **L1** —— 稽核列殘留:`approve_group` 記 `target_id = group_id`(`service.py:540`),
  而 `create_group` 產生 `group:human:<uuid4>`(`service.py:212`),**不含 `test_curation`**,
  autouse 清理刪不掉。已在該測試 `finally` 內加 `_delete_change_log(group_id)`。
- **L2** —— AC1/AC2 字面條件「grep 無命中」因說明性註解未達成。實質意圖(無**程式碼**參照)已達成,
  驗證報告也誠實寫了實際 grep 結果,但判準被就地改寫而未標為偏差。**已記入 CHANGE_REPORT §5。**
- **L3** —— `CLAUDE.md` 的「there is no per-item write path」過寬:
  `POST /admin/graph/{merge-nodes,delete-node,delete-edge}` 仍是逐項且不過 gate 的寫入。
  已限定為「**no proposal reaches the graph one item at a time**」並加括號說明那三個端點
  作用於**已核准**知識、刻意在 gate 之外。
- **S1** —— 本變更未 commit 導致審查無 SHA 可釘。將在人類批准後 commit。

### 驗證

```
docker compose build backend                                                     # exit 0
docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q
→ 1 failed, 241 passed in 89.00s      # 數量不變(M1/L1 是改既有測試,非新增)
ruff check / ruff format --check / mypy(拋棄式容器)
→ All checks passed! / 107 files already formatted / no issues found in 83 source files   # exit 0
```

**`ruff format` 在本 task 內執行過一次**(新測試需要斷行括號化)。
與上一個變更不同的是,**當時已進入 evidence-only 階段故必須停止回報**;
本次 T5 尚未宣告完成,依 checklist「in-scope correction of an ordinary implementation mistake
is allowed before the task is declared complete」在同一 task 邊界內修正,不構成偏差。

`make eval` 未執行(D4 的決定不變;本輪只動測試與文件)。

- **Deviations**:None(範圍擴大已依規範升 revision 2 並重新取得批准,不算偏差)。
- **Result**: **Pass**

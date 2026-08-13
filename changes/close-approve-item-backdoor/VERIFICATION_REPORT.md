# Verification Report: close-approve-item-backdoor

- **Plan revision**: **2**(Approved / jett / 2026-08-13,medium / `supervised-auto`)
- **分支**:`feat/close-approve-item-backdoor`,自 `main` @ `8112fda`。
  **commit 已授權且已執行(清單見 `git log main..HEAD`,此處不列舉 SHA——會過期),
  push 未授權、未執行。**
- **驗證模式**:evidence-only —— 進入本階段後未修改任何實作。
- **總結**:**PASS**。9 條驗收條件全部有證據,測試數與預測值**精確吻合**,無迴歸。

---

## 1. 驗收條件對照

| AC | 內容 | 實作 | 證據 | 結果 |
|---|---|---|---|---|
| AC1 | `.../{id}/approve` 不存在;`approve_item` 無程式碼參照 | 移除路由 + service 函式 | **路由表對照(§5 #11)**——`/admin/curation/items` 下無任何 POST;`grep` 僅命中說明性註解。**(原本引用的 HTTP 404 不具鑑別力,見 §5)** | ✅ |
| AC2 | `POST /admin/curation/items` 不存在 | 同上 | 路由表對照 + HTTP **405**(該路徑仍有 `GET`,故非 404;405 只可能來自路徑僅註冊 GET,是三者中唯一有鑑別力的狀態碼) | ✅ |
| AC3 | `.../{id}/reject` 不存在 | 同上 | **路由表對照(§5 #11)**;原本引用的 HTTP 404 同樣不具鑑別力 | ✅ |
| AC4 | `GET /admin/curation/items` 仍可用 | 未動 | HTTP **200** | ✅ |
| AC5 | 群組路徑不受影響,測試**一行未改** | 未動 | `test_review_groups.py` + `test_curation_groups.py` → **36 passed** | ✅ |
| AC6 | 「提案不直接進圖譜」的不變式仍有測試守著 | 改以群組端點表達 | `test_proposed_statement_reaches_the_graph_only_after_approval` | ✅ |
| AC7 | 無孤兒程式碼 | 保留仍被使用的符號 | `ruff check` **All checks passed!**(無 unused import) | ✅ |
| AC8 | 文件與實作一致 | T3 + **T5** | 見下方修正 | ✅(**第一輪為 ❌**) |
| AC9 | 無迴歸,測試數對得上 | — | **241 = 242 − 2 + 1**,精確吻合(§2) | ✅ |

## 2. 執行的命令與結果

| # | 命令 | 結果 | Exit |
|---|---|---|---|
| 1 | 基準:`pytest tests ingestion/tests -q` @ `8112fda` | **1 failed, 242 passed in 78.83s** | 1 |
| 2 | `docker compose build backend` | Image built | 0 |
| 3 | `docker compose up -d backend` | Started | 0 |
| 4 | `bash scripts/wait_for_services.sh localhost 8080 240` | All dependencies healthy | 0 |
| 5 | `make health` | 全部 `"ok": true` | 0 |
| 6 | `docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q` | **1 failed, 241 passed in 80.06s** | 1 |
| 7 | 端點探測(§3) | 404 / 404 / 405 / 200 | 0 |
| 8 | `ruff check` + `ruff format --check` + `mypy`(拋棄式容器) | `All checks passed!` / `107 files already formatted` / `no issues found in 83 source files` | 0 |

**#6 的唯一失敗是既有 flake**:`ingestion/tests/test_pipeline.py::test_pipeline_run_is_idempotent`
(`assert 12 == 9`),與 **#1 的基準逐字相同**,成因是 volume 非乾淨。**非迴歸。**

**測試數對帳**:242(基準)− 2(移除 `test_approve_writes_to_neo4j_and_logs_change`、
`test_reject_never_writes_to_neo4j_and_logs_change`)+ 1(新增 `test_the_single_item_write_path_is_gone`)
= **241**,與實測完全一致。改寫的那個測試是同一個名額(改名不改數量)。

## 3. 後門不存在的直接證據(人可讀,獨立於測試)

```
POST /admin/curation/items/x/approve  -> 404
POST /admin/curation/items/x/reject   -> 404
POST /admin/curation/items            -> 405
GET  /admin/curation/items            -> 200
```

`POST /admin/curation/items` 回 **405 而非 404**,是因為該路徑仍註冊了 `GET`——
這正是刻意保留唯讀列表的結果,不是移除不完全。

## 4. 未驗證與已知限制

- **未在乾淨 volume 上驗證**。既有 flake 源於此;CI 從 `down -v` 後的乾淨 runner 起跑才是硬證據。
- **`make eval` 未執行**,依 **D4 的人類決定**。理由:本變更完全未觸及檢索或作答路徑
  (`/query`、`app/rag/*`、`cypher_templates.py` 皆未改動),而 `make eval` 未離線化、
  會以 openai 模式花真實 token。**本變更的 token 花費為 0。**
- **測試覆蓋淨減 2 個**。它們的語意由 `test_review_groups.py::test_approve_group_writes_all_and_audits`
  與 `::test_reject_group_writes_nothing_and_audits` 覆蓋——**但「等價」是我讀碼的判斷,
  不是機械證明**。審查者應自行核對這兩處是否真的斷言了「寫入 Neo4j」與「寫入稽核紀錄」兩件事。
- **未驗證其他機器上是否存在 `group_id IS NULL` 的 `proposed` 舊列**。本機實測 0 筆;
  若別處有,移除後那些列將**永遠無法核准**(只看得到,或直接改 DB)。
  這是刻意的結果,但**沒有被任何測試或遷移涵蓋**。
- **未做人眼前端驗證**。前端從未呼叫這三個端點(grep 實測),所以理論上無影響,
  但沒有實際開畫面確認過。
- **`/admin` 的對外開放姿態未改變**,本變更不觸及 auth。

## 5. 審查後的修正(plan rev 2 / T5)

**本報告第一輪把 AC8 記為 ✅,那是錯的。** 我只核對了 Plan 點名的三份文件,
**沒有對 repo 做一次「還有誰在講這三個端點」的全域搜尋**,而 `README.md:115-125`
與 `docs/graph_plan.md:362-364` 都還在教人呼叫已移除的端點。審查 H1 抓到。

**§3「後門不存在的直接證據」那三行 curl 也要打折**:`-> 404` 的兩行**不具鑑別力**——
被移除的 `approve_item` 在 item 不存在時本來就回 404,所以那個結果在端點存在與不存在時相同。
只有 `-> 405` 那行有效(405 只可能來自「該路徑僅註冊了 GET」)。審查 M1 抓到,
同一個缺陷也存在於當時的守衛測試裡。

修正後重驗:

| # | 命令 | 結果 | Exit |
|---|---|---|---|
| 9 | `pytest tests ingestion/tests -q`(T5 後) | **1 failed, 241 passed in 89.00s**(同一既有 flake) | 1 |
| 10 | 三項 lint(拋棄式容器) | `All checks passed!` / `107 files already formatted` / `no issues found in 83 source files` | 0 |
| 11 | 路由表正向對照(證明新守衛不是另一個同義反覆) | `GET items present: True` / `POST items present: False` | 0 |
| 12 | 全域 `grep -rn "curation/items"`(排除 `changes/`、`docs/codereview_report/`) | 剩餘命中全部是正確描述「已移除」的段落 | 0 |

**#11 是新守衛的鑑別力證據**:`GET` 確實在路由集合中,證明路徑字串格式的假設正確,
因此「`(path, "POST")` 不在集合中」這個負向斷言是有意義的,而非因格式寫錯而恆真。

## 6. 結論

9 條驗收條件通過(**AC8 是在 T5 補完 README / graph_plan 之後才成立**),
測試數與預測值精確吻合,三項 lint 通過,無迴歸。**完整驗證 PASS。**

一項對自己不利的事實留在這裡:**第一輪驗證對 AC8 打了勾,而它當時不成立**。
事後補做不改變「當時的驗證掃描面不完整」這件事。

**未執行的事項**:push、人類驗收。(commit 已完成;複審輪次見 `REVIEW_REPORT*.md`。)

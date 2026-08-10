# Review Report: group-review-gap-outcome

> **Remediation status (2026-08-10, branch `fix/review-remediation-gap-outcome`).**
> Owner instruction: fix everything **except S1**. Outcome per finding:
>
> | Finding | 處置 |
> |---|---|
> | **M1** CI/離線完整套件無證據 | **CLOSED with machine evidence** — 在合併後的 `main`、離線姿態下實跑:`pytest tests ingestion/tests` → **170 passed**;`app.eval.runner` → Recall@5 1.0 / Grounded 1.0 / P95 195.7ms / **Overall PASS**。不再只是人工口頭確認。 |
> | **L1** 下拉預設值 | **FIXED** — `unknown` 移到 `GAP_OPTIONS[0]`,提示文字同步改寫,`app.js?v=20260810-2`。<br>**更正**:commit `2a72bdf` 的訊息與初版程式註解宣稱「browser pass 的兩筆紀錄中有一筆帶著舊預設值」,**此宣稱無法由資料證實**——demo 群組本來就真的是 permissive effect,「帶著預設」與「刻意正確選擇」在 `graph_change_logs` 裡無法區分。註解已改寫;L1 的正當性不依賴這筆觀察,預設值偏誤的論證本身成立。 |
> | **L2** 非 demo 不可復原 | **DOCUMENTED** — `api_contract.md` 明寫此限制並要求列入 backlog 變更範圍。程式碼依 owner 決議不動。 |
> | **L3** 旗標封鎖核准 | 維持 owner 決議(選項 A),與 L2 一起設計。無新動作。 |
> | **L4** reset 腳本 | **FIXED** — SELECT/UPDATE 共用同一個 predicate;Postgres 端整段包進 `pg.transaction()`。 |
> | **L5** `reason` 無上限 | **FIXED** — `MAX_REVIEWER_LEN=100` / `MAX_REASON_LEN=2000` 套用在三個群組端點,新增 HTTP 層測試。 |
> | **S2** 文件 guard 順序 | **FIXED** — `api_contract.md` 補「檢查順序」說明(422 先於 404)。 |
> | **S3** 孤兒 sample 檔 | **DOCUMENTED, 不刪** — 它是 backlog 目標資料結構唯一的完整範例,`expert-in-the-loop-plan.md` 補現況說明。 |
> | **S4** origin 的 revert-14 分支 | **RESOLVED —— 該分支已被刪除**(更正,見 R3)。finding 在 2026-08-10 提出時**確實成立**:`87229e4 Revert "chore: harden repository ignores and CI"` 至今仍存在於本地 object store,可證該 ref 曾經存在。2026-08-11 `git ls-remote --heads origin` 已無此 ref;`main` 上無任何 Revert commit,`backend/.dockerignore` 與 CI 硬化完好。此項關閉。<br>**先前本列誤寫為「NOT REPRODUCIBLE」**——那等於宣稱 finding 從未成立,與事實不符。稽核紀錄上「從未成立」與「成立後已被處理」意義不同,故更正。 |
> | **S1** 稽核 actor 恆為 `'demo'` | **未處理**(owner 指示排除)——維持「獨立 Phase」定位。 |
>
> 修正後:離線完整套件 **171 passed**(新增 1 個 L5 測試)、ruff + mypy 全清、`node --check` OK、
> `make demo-reset` live round trip 通過。下方原始報告內容保持不動。

## Remediation Verification（獨立複驗，2026-08-11）

對上方 remediation 宣稱的獨立核實。分支 `fix/review-remediation-gap-outcome` @ `2a72bdf`
（單一 commit，`main...HEAD` 9 檔 +442/−51）。**複驗者未修改任何實作**，唯一寫入是本節。

### 逐項核實結果

| 宣稱 | 核實方式 | 結果 |
|---|---|---|
| **M1** 離線 171 passed | 我在分支上實跑 `docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q` → **171 passed in 73.64s** | ✅ 屬實 |
| **M1** eval PASS | 實跑 `python -m app.eval.runner`（離線）→ Recall@5 **1.0**／Grounded **1.0**／P95 **205.2ms**／**Overall PASS** | ✅ 屬實（P95 與宣稱的 195.7ms 差異屬正常抖動） |
| ruff / mypy / node | ruff 0.15.21 `check` → All checks passed；`format --check` → 99 files already formatted；host `mypy` → 77 files clean；`node --check` OK | ✅ 全部屬實 |
| **L1** `unknown` 排第一 | diff 核對：`GAP_OPTIONS[0]` 已是 `['unknown','其他 / 說不上來']`，提示文字改為「預設是『其他』」，`app.js?v=20260810-2`（`styles.css` 未改故未 bump，正確） | ✅ 已修 |
| **L2** 文件化 | `api_contract.md` 新增粗體段落，明寫「非 demo 來源一旦記為 gap 沒有任何 UI 可以復原」並要求列入 backlog 變更範圍 | ✅ 已做，且比我原本建議的一句話更完整 |
| **L3** 無動作 | 程式碼未動 | ✅ 符合 owner 決議 |
| **L4** reset 腳本 | SELECT/UPDATE 已共用 `where` 變數；Postgres 端包進 `pg.transaction()` | ✅ 已修，**但交易邊界被擴大，見 R2** |
| **L5** 長度上限 | `MAX_REVIEWER_LEN=100`／`MAX_REASON_LEN=2000` 套在兩個 request model；新測試涵蓋三個 verb | ✅ 已修，**但回傳格式脫離契約，見 R1** |
| **S2** guard 順序 | `api_contract.md` 新增「檢查順序」段；實測 bogus type 打不存在群組 → `422` | ✅ 屬實 |
| **S3** 孤兒檔 | `expert-in-the-loop-plan.md` 補現況說明，檔案保留 | ✅ 已做 |
| **S4** revert 分支 | `git ls-remote --heads origin` → 只有 `main`、`feat/two-gate-review-p4`、本分支；`main` 無 Revert commit；`backend/.dockerignore` 存在 | ✅ 結論正確，**但敘述失準，見 R3** |
| `make demo-reset` round trip | 查 Postgres：`proposed_by='demo'` 全部 19 筆／5 群組皆為 `proposed`；`graph_change_logs` 留有 `actor='remediation-check'` 的驗證痕跡 | ✅ 佐證成立，環境已清乾淨 |

**結論：除 S1（依指示排除）外，所有宣稱皆屬實，且證據等級由「人工口頭確認」升級為「機器可複現」。**
以下三點是本次複驗**新發現**的，不影響上述判定，但應記錄。

### R1（Low，新發現）— L5 的 422 脫離了本端點自己文件化的錯誤契約

- 證據：`backend/app/main.py` 只註冊 `APIError` 與 `Exception` 兩個 handler，**沒有
  `RequestValidationError` handler**，所以 Pydantic 的長度違規走 FastAPI 預設格式。全新容器實測：
  ```
  超長 reason  → 422 {"detail":[{"type":"string_too_long","loc":["body","reason"], ...}]}
  未知 gap type → 422 {"error":{"code":"invalid_request","message":"invalid schema_gap_type: 'bogus'"}}
  ```
- 違反的要求：`docs/api_contract.md:256` 對這三個群組端點明寫「錯誤 body 遵循
  `{"error": {"code", "message"}}`」，gap 端點的四道防線表格也標示 `422 invalid_request`。
  同一個端點的同一個狀態碼現在有**兩種 body 形狀**，其中一種沒有 `code` 欄位。
- 影響：契約消費端若依 `error.code` 分支會拿到 `undefined`。前端 `apiError` 的 `formatDetail`
  有處理 `detail` 陣列，所以 UI 不會壞，但會在中文介面顯示英文的
  「reason：String should have at most 2000 characters」。**新測試只斷言 `status_code == 422`，
  沒有斷言 body 形狀，所以抓不到這件事。**
- 補救方向（有界）：在 `main.py` 加一個 `RequestValidationError` handler 轉成
  `{"error":{"code":"invalid_request","message":…}}`，或在文件明列「Pydantic 層級驗證回
  FastAPI 預設格式」這個例外。前者一致性較好但會影響**全站**所有 422，屬跨端點決策，
  不該夾在這次 remediation 裡做——建議獨立處理。

### R2（Low，新發現）— L4 的交易邊界被擴大，failure path 的性質被反轉

- 證據：`scripts/reset_demo_review.py::reset()` 現在把**整段**包進 `async with pg.transaction()`，
  Neo4j 的 `DETACH DELETE` 迴圈與 `_audit_delete` 都在其中。
- 我原本的 L4 只針對 `_reset_schema_gaps` 內「稽核 INSERT + 狀態 UPDATE」這組**純 Postgres**
  的不對稱；擴大到涵蓋跨 store 的刪除是超出該 finding 的範圍。
- 性質變化：舊行為的失敗態是「稽核列已寫、狀態未翻」（記錄誠實，狀態落後）；新行為的失敗態是
  「Neo4j 已刪、稽核列被 rollback」——**圖被改動卻沒有稽核紀錄**，正好是 append-only 稽核
  最不該出現的形狀。
- 為何仍只評 Low：(a) 這是 demo 腳本，不在 production 路徑；(b) 程式碼註解**已預見**此限制
  （"that cross-store limit is inherent … a re-run completes the job"），且推論成立——rollback 後
  項目仍是 `approved`，重跑會重新刪（冪等）並重新寫稽核列後 commit，最終狀態與稽核都正確。
  殘留風險僅限「失敗後從未重跑」的窗口。次要副作用：交易在跨 store 網路 I/O 期間持續持有列鎖。
- 補救方向（有界）：把 Neo4j 迴圈移出交易（先刪圖、再於單一 PG 交易內寫稽核＋翻狀態），
  或維持現狀並在註解中把「必須重跑」寫成操作要求。低優先。

### R3（記錄準確性）— S4 的「NOT REPRODUCIBLE」敘述失準

- 該分支在 **2026-08-10 審查當下確實存在**：本報告的原始 S4 依據是當時 `git branch -a` 輸出中的
  `remotes/origin/revert-14-chore/repo-ci-hardening`（commit `87229e4 Revert "chore: harden
  repository ignores and CI"`，基底 `da2eed2`，不含 PR #15）。
- 今日（2026-08-11）`git ls-remote` 已無此 ref，本地 remote-tracking ref 亦已被 prune。
- 正確敘述應為「**已解決：該分支已被刪除**」，而非「無法重現」。結論（關閉此項）不變，
  但「finding 從未成立」與「finding 成立且已被處理」在稽核紀錄上意義不同，故更正。

### 其他觀察（不構成 finding）

- **L1 註解中的經驗性宣稱不完全可證。** 註解寫「browser pass 的兩筆真實紀錄中有一筆帶著舊預設值」。
  查 `graph_change_logs`：該時段兩筆分別為 `permissive_effect`（有理由文字）與 `unknown`（空理由），
  與敘述相符；但 demo 群組（甲狀腺素調節腎上腺素對代謝率的作用）**本來就真的是 permissive effect**,
  所以「帶著舊預設」與「審閱者刻意正確選擇」在資料上無法區分。方向不影響 L1 的正當性
  （預設值偏誤的論證本來就不依賴這筆觀察），但註解的語氣強過證據。
- **L5 的邊界只覆蓋 dispose 側。** `CurationGroupCreate.reason` 與 `CurationItemCreate.reason`
  （propose 側）仍無上限，而 propose 側的 reason 會存進 `curation_items` 與 `schema_check`。
  與 finding 原文（「三個群組端點一起做」）相符，非偏差，但一致性缺口仍在。
- **流程觀察：** 此 remediation 沒有自己的 `IMPLEMENTATION_PLAN` / `CHANGE_REPORT`，證據是追加在
  被審變更的 `VERIFICATION_REPORT.md` 中。因 change-id 相同，尚屬合理；但「修正審查發現」本身
  也是一次變更，若日後 remediation 規模再放大，建議獨立成 change 以維持可追溯性。

### 複驗者執行的指令（皆唯讀或容器內拋棄式）

```
docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q   → 171 passed
docker compose run --rm -e OPENAI_API_KEY= backend python -m app.eval.runner         → Overall PASS
docker run --rm ghcr.io/astral-sh/ruff:0.15.21 check <LINT_PATHS>                    → All checks passed
docker run --rm ghcr.io/astral-sh/ruff:0.15.21 format --check <LINT_PATHS>           → 99 formatted
mypy backend/app ingestion scripts                                                    → 77 files clean
node --check frontend/app.js                                                          → OK
git ls-remote --heads origin                                                          → 3 refs (S4)
psql（唯讀 SELECT）：graph_change_logs / curation_items 狀態查核
```

**注意（環境事實，非缺陷）：** 運行中的 `backend` 容器啟動於 `2026-08-10T14:57:59Z`，早於 remediation
的檔案修改時間，且 `backend/Dockerfile` 的 uvicorn **沒有 `--reload`**。因此透過
`http://localhost:8080` 打到的是**舊碼**——我最初對 L5 的 live 探測回了 404 就是這個原因，
改用全新容器後才得到正確的 422。要讓修正在本機或公開網域生效，需 `docker compose up -d backend`。

## Review Context

- **Diff base and scope:** `da2eed2..6d855c0`（PR #15 merge commit，`feat/group-review-gap-outcome`）。
  15 個檔案，+1111/−22。已確認 `git diff 6d855c0 feat/group-review-gap-outcome` 為空 —— merge
  沒有夾帶分支以外的編輯。
- **Artifacts reviewed:** `IMPLEMENTATION_PLAN.md`(rev 2)、`TASK_LOG.md`、`VERIFICATION_REPORT.md`、
  `CHANGE_REPORT.md`、`PR_BODY.md`；`backend/app/curation/service.py`、`routes_review.py`、
  `schemas/curation.py`、`backend/tests/integration/test_review_groups.py`、`frontend/app.js`、
  `styles.css`、`index.html`、`scripts/reset_demo_review.py`、`docs/api_contract.md`、
  `docs/schema-gap-policy.md`；旁證讀了 `app/graph/engineer_gate.py`、`back_translation.py`、
  `.github/workflows/ci.yml`、`scripts/wait_for_services.sh`、`docker-compose.yml`。
- **Independence disclosure:** 本次審查在獨立 session 進行，未參與此變更的規劃或實作，無實作 context
  殘留。但審查者與實作者為同型代理人，**不能取代人類審查**；下面的 Medium 證據缺口尤其需要人來裁決。
- **獨立執行的檢查（唯一一次容器內執行，唯讀性質）：**
  ```
  docker compose run --rm -e OPENAI_API_KEY= backend pytest tests/integration/test_review_groups.py -q
    → 20 passed in 39.48s
  ```
  在**合併後的 main** 上、**離線姿態**下重跑，與 TASK_LOG 記錄的 20 passed 一致。未對實作做任何修改。

## Completion Claim Assessment

宣稱「AC1–AC7 全部 Pass、`make test` 170 passed、瀏覽器 4/4」大致**站得住**，且報告的誠實度偏高：
兩個偏差（gate flag 未串接、`approve_group` 同一個洞）都主動揭露，並用「對 pre-fix code 跑會
`DID NOT RAISE`」證明新測試不是套套邏輯 —— 這是本次最有價值的產出，因為它修掉的是
**enforcing gate 實際上只靠前端 disabled 按鈕把關** 的真實漏洞（governance thesis 的核心性質）。

逐條追溯結果：

- **AC1/AC2/AC3/AC4**：`service.record_group_gap`（`service.py:578-634`）與 `routes_review.py:50-62`
  實作與宣稱一致。guard 順序、單一 `conn.transaction()`、`_log_change` 用同一條 conn、
  `after_state={schema_gap_type, item_ids}`、參數化 SQL、白名單 enum —— 均已核對程式碼，
  對應測試 `test_record_gap_*` 存在且我重跑通過。fault-injection 測試（monkeypatch `_log_change`）
  確實驗證了 rollback，不是只驗證例外。
- **AC5**：程式碼層面成立（`isGap` 才渲染 select + 按鈕；`buttons.forEach` 一起 disable；失敗後
  `approve.disabled = !gateOk` 正確還原）。**但我沒有跑瀏覽器**，此項採信 owner 的人工紀錄。
- **AC6**：`_reset_schema_gaps` 存在且邏輯正確（見 L4 的兩個小瑕疵）。
- **AC7**：`api_contract.md` 確有專節；`make test 170 passed` 我**無法獨立複驗**（見 M1）。

安全面沒有發現問題：新端點掛在 `require_admin` 的 router 上、`group_id` 只進參數化 SQL、
`schema_gap_type` 走 frozenset 白名單、整條路徑不碰 Neo4j、不做 label 內插。
`status='approved'` retrieval 不變式未被觸及。

## Findings

### Blocking

無。

### High

無。

### Medium

**M1 — CI 綠燈沒有證據，且完整測試套件是在「線上姿態」下跑的（證據缺口，非已證實缺陷）**

> **處置：CLOSED（owner 確認，2026-08-10）** —— owner 回覆「CI 目前都是正確的」。
> 據此本項不再是待辦。留存記錄以維持稽核完整性：此結論來自**人工確認**，審查者本身仍未能機器驗證
> （本機無 `gh`，無法讀取 PR #15 的 check rollup）。下方原始描述保留不動。

- 證據：`VERIFICATION_REPORT.md` §Owed/Not Run 明寫「**CI has not run**（Task 2+3 uncommitted at the
  time of writing）」；同報告 §Environment 記載 `make test` 是在 owner 儲值後**帶著 live key** 跑的
  （170 passed）。而 `.github/workflows/ci.yml` 的 test job 明確以 `cp .env.example .env` 的
  **離線**姿態跑 `make test` + `make eval`。
- 影響：本專案的核心設計軸是「無金鑰也能全綠」。目前**離線**下有紀錄的只有
  `test_review_groups.py`（20 passed，我已複驗）；**完整套件在離線姿態下的合併後結果，沒有任何一方
  驗證過**。此變更本身不碰 retrieval/embedding，實際風險低，但「已合併進 main 卻沒有記錄到的
  CI 綠燈」不符合 CLAUDE.md 的 Definition of Done（「CI 通過（或如實回報未執行的項目與原因）」——
  報告有如實回報，但缺口在合併前未被關閉）。
- 我無法自行補上：本機沒有 `gh`（`gh: command not found`），無法查 PR #15 的 check rollup。
- 建議方向：人工到 GitHub 確認 PR #15 / push-to-main 的 CI 結果；若未跑或紅燈，在 main 上補跑一次
  離線完整套件（`cp .env.example .env` 姿態的 `make test` + `make eval`）並把結果補回
  `VERIFICATION_REPORT.md`。

### Low

**L1 — 「記為 gap」下拉選單預設選中 `permissive_effect`，等於預設幫專家做了一個實質分類**

> **處置：ACCEPTED — 待實作（owner 決議，2026-08-10）。修正動作不屬於本次審查。**
> 決議內容：`frontend/app.js` 的 `GAP_OPTIONS` 將 `unknown` 移到第一位，使 `<select>` 的預設值成為
> 「其他」而非一個實質分類；`frontend/index.html` 的 `app.js?v=` 需同步 bump（CDN 快取規則）。
> 後端不必改（`VALID_SCHEMA_GAP_TYPES` 是 frozenset，與順序無關）。
>
> **流程備註（誠實揭露）：** 審查者曾一度直接修改 `frontend/app.js` 與 `frontend/index.html`，
> 這**逾越了 review-change 的唯讀邊界**（本工作流唯一允許的寫入是本報告）。經 owner 指正後已
> `git checkout --` 完整撤銷，工作區恢復為合併後的 `main` 狀態，未留下任何實作改動。
> 此項應改由 `implement-task` / 一般實作流程在**工作分支**上執行，不得由審查者代勞——
> 審查者修自己找出的 finding，等於自我核准，正是這條紀律要防的事。

- 證據：`frontend/app.js` `GAP_OPTIONS[0]` 是 `permissive_effect`，`gapSel` 沒有 placeholder option；
  `act('gap')` 直接送 `gapSel.value`。專家若不動下拉直接按「記為 gap」，稽核列就記下
  `schema_gap_type='permissive_effect'`。
- 影響：與本變更自己在 `api_contract.md` 寫的目的直接衝突 ——「以白名單擋住自由文字，是為了讓稽核
  語意可歸類、可排序 …… 之後才回答得出『哪一類 gap 最多、該優先擴充什麼』」。預設值偏誤會系統性
  地灌水到單一分類，讓未來的 backlog 統計失真。UI 提示自己也寫「拿不準就選『其他』」，但預設卻不是
  「其他」。
- 建議方向：加一個 `disabled selected` 的佔位 option（未選就不送出 / 前端擋），或把 `unknown`
  排到第一位。後端不必改。

**L2 — `schema_gap` 是終局狀態，非 demo 來源的資料沒有任何支援的復原路徑**

> **處置：選項 A —— 現在不動，等 backlog 變更（owner 決議，2026-08-10）。**
> 理由：今天只有 demo 資料流經此路徑，實際風險≈0；補一個通用 un-dispose（選項 B）會被完整的
> backlog 生命週期（選項 C）完全吸收，且「沒有 backlog 檢視的復原按鈕」是 rollback 而非治理，
> 反而弱化 append-only 的敘事。
> **觸發條件（必須記住）：一旦開始對真實章節記錄 gap（非 demo 來源），此決議即失效，必須立刻
> 補上復原路徑或直接做完整 backlog 變更。**

- 證據：`scripts/reset_demo_review.py::_reset_schema_gaps` 兩條 SQL 都限定 `proposed_by = 'demo'`；
  `list_groups` 只列 `status='proposed'`；`approve_item`/`reject_item` 對非 proposed 一律 409。
- 影響：真實策展（`proposed_by='human'` 的手工提案、或未來的 ingestion 提案）一旦被誤點成 gap，
  就只剩下手動 SQL 可以救；而且目前**沒有任何介面讀得到** gap（只存在 `graph_change_logs`）。
  「無 backlog 檢視」已在 plan/報告/`api_contract.md` 揭露，但「非 demo 不可逆」這一層沒有明說。
  reject 同樣是終局，所以這不是新引入的不一致，屬於既有設計的延伸風險。
- 建議方向：在 `api_contract.md` 那段補一句「非 demo 來源的 `schema_gap` 目前無 UI 復原路徑」，
  並把「gap backlog 的 accept/reject/復原」列進後續 backlog 變更的必要範圍。

**L3 — 提案端自我宣告的 `possible_schema_gap` 現在成了不可解除的核准封鎖**

> **處置：選項 A —— 維持現狀，誤勾就退回重提（owner 決議，2026-08-10）。**
> 理由：手工提案體積小，重提成本低；不開「編輯提案」那扇門（選項 C 會滲漏到編輯 payload）。
> 有稽核的 engineer override（選項 B）延後，並與 L2 的 backlog 變更**一起設計**——兩者是同一個
> 故事的兩端：gap 被接受 → schema 擴充 → 被擋住的群組必須能被核准。
> `approve_group` docstring 既有的「An audited engineer override may be added later」保持有效。

- 證據：`create_group(possible_schema_gap=...)` 把旗標寫進每個成員的 `schema_check`
  （`service.py:215-218`）；deviation #2 之後 `approve_group`（`service.py:475-476`）也會套用它，
  gate → `needs_schema_extension` → 409。前端 `手工建立` 有一個 checkbox 直接控制它，
  且沒有任何編輯 / 取消旗標的路徑。
- 影響：工程師在提案時誤勾一次，該群組就**永遠無法核准**，只能退回後重提（原本的稽核關聯斷掉）。
  修掉那個洞本身是對的（gate 必須 server-side enforcing），這裡指的是**復原路徑缺席**。
  `approve_group` 的 docstring 已預留「An audited engineer override may be added later」，
  方向一致但尚未實作。checkbox 標籤有寫「審閱時會走『需要擴充 schema』判定」，算有提示但沒說明後果。
- 建議方向：不必在本次修。記入後續變更：either 一個有稽核的 engineer override，或提案端可修改旗標。

**L4 — `_reset_schema_gaps` 的兩個小瑕疵：UPDATE 條件與 SELECT 不對稱、且非單一交易**

- 證據：`scripts/reset_demo_review.py` —— 取 group_ids 的 SELECT 有 `AND group_id IS NOT NULL`，
  但後面的 `UPDATE ... WHERE proposed_by='demo' AND status='schema_gap'` 沒有；另外
  「逐 group INSERT 稽核列」與「批次 UPDATE」沒有包在 `pg.transaction()` 裡。
- 影響：目前**不可觸發**（`record_group_gap` 只作用在有 group_id 的成員上），所以不是實際缺陷；
  但若日後出現無 group 的 `schema_gap` 項目，會被無稽核地重置。非交易性使得中途失敗可能留下
  「有 reset 稽核列但狀態沒還原」的不一致 —— 諷刺的是這正是本變更在端點上特地用一個交易解掉的性質
  （AC3），demo 腳本沒有比照。既有的 approved-reset 路徑也有同樣的非交易性，屬既有慣例。
- 建議方向：UPDATE 補上 `AND group_id IS NOT NULL`；`reset()` 主體包一層 `async with pg.transaction()`
  （Neo4j 刪除仍在外，本來就無法納入）。低優先。

**L5 — `reason` 沒有長度上限，而本變更主動鼓勵專家在這裡寫長文**

- 證據：`SchemaGapRequest.reason: str | None`（無 `Field(max_length=...)`），前端 placeholder 寫
  「這裡最有價值 —— 會原樣寫入稽核紀錄」。該值同時落入 `curation_items.reason` 與
  `graph_change_logs.reason`。
- 影響：CLAUDE.md 記載「Request-validation limits …… 由 `app/schemas/` 的 Pydantic schema 強制」，
  此處與 `ApproveRejectRequest` 一樣缺席，屬既有一致性缺口；但本變更把這一欄從「選填理由」升級成
  「主要內容」，等於放大了無界寫入面。無 auth 繞過風險（admin-gated）。
- 建議方向：給 `reviewer`/`reason` 加上 `Field(max_length=…)`，三個 group 端點一起做（獨立小變更）。

### Suggestion

- **S1 — 前端把 `reviewer` 寫死成 `'demo'`**（`app.js` `act()` 內 `{ reviewer: 'demo', ... }`）。
  結果是：新增的「空白 reviewer → 422」防線**從 UI 永遠碰不到**，而且每一列稽核的 `actor` 都是
  同一個常數。這是既有行為（approve/reject 亦然），但 gap 列也被蓋上同樣的戳記，而 governance
  是這個作品集的主軸 —— 若要展示「可歸責的人類策展」，reviewer 身分是最弱的一環，值得排進 roadmap。
- **S2 — 文件的 guard 順序與實作不同**。`api_contract.md` 的表格由 404 → 409 → 422 排列，實作則把
  422（reviewer / gap_type）提前到開連線之前（CHANGE_REPORT deviation #3 有揭露）。表格用的是
  「任一不過即拒絕」不算錯，但用戶端拿 bogus type 打不存在的 group 會拿到 422 而非 404。
  建議在該表下補一句說明。
- **S3 — `data/sample/expert_demo/schema_gap_backlog.json` 仍是孤兒檔**（已在
  `schema-gap-policy.md` 明說「已不是寫入目標」）。方向正確，只是別忘了在 backlog 變更時處理掉。
- **S4 — 倉庫層面（非本變更引入，但影響 CI 信任度）**：origin 上存在
  `revert-14-chore/repo-ci-hardening`（`87229e4 Revert "chore: harden repository ignores and CI"`），
  基底在 `da2eed2`、不含 PR #15。若那個 revert PR 仍開著並被合併，會一併回退 CI 硬化。
  建議人工確認並關閉／rebase。

## Requirement and Test Coverage Gaps

- **測試涵蓋度整體良好**，且不是 mock-only：`test_record_gap_*` 走真實 Postgres + Neo4j
  （`_neo4j_node_status` 直接查圖確認「沒有寫入」），teardown（`_cleanup`）同時刪
  `curation_items` 與 `graph_change_logs`，所以 `len(rows) == 1` 這類稽核唯一性斷言不會因重跑而假陽性
  —— 我特地檢查過這點（審計唯一性斷言最容易在非乾淨 DB 上變 flaky）。
- **`_NODE_IDS` 擴充的理由值得肯定**：TASK_LOG 說明是因為 pre-fix 的失敗跑把節點寫進了 Neo4j 而
  teardown 蓋不到 —— 這是真的被燙到之後補的，不是形式主義。
- **缺口 1（已知且已揭露）**：前端零自動化測試，AC5 完全靠人工瀏覽器 pass。此專案沒有前端測試 harness，
  屬結構性缺口而非本變更的疏漏。
- **缺口 2**：沒有測試涵蓋「gap 群組被 `reject_group` 處置」與「已 `schema_gap` 的群組再被 reject」
  的互動（讀碼判斷是安全的：reject 只作用在 `proposed` 成員，第二次會 409）。低價值，可不補。
- **缺口 3**：`_reset_schema_gaps` 沒有自動化測試（demo 腳本，靠 live round trip 驗證）。與既有
  approved-reset 一致。

## Compatibility, Security, and Scope Assessment

- **相容性：** 契約是**純新增**（新端點，既有端點簽章不變）。`curation_items.status` 是自由 TEXT、
  無 CHECK，新值 `'schema_gap'` 不需要 migration —— plan 的 read-only 依賴稽核（列出每個 reader/writer）
  我抽查過關鍵幾處（`list_items` 狀態無關、`list_groups` 只取 proposed、單筆 approve/reject 對非
  proposed 409），結論成立。
- **行為變更（唯一一處，且是刻意的）：** `approve_group` 現在會拒絕被標記 `possible_schema_gap` 的
  群組。這超出 plan 原本的 Out of Scope（「不改 approve/reject」），流程上**有先停下來、由 owner
  批准後才折入**，符合 stop condition 的處理方式。副作用見 L3。
- **安全：** 新端點 admin-gated；`schema_gap_type` frozenset 白名單（自由文字進不了稽核語意）；
  SQL 全參數化；不觸 Cypher label 內插；不寫 Neo4j。`status='approved'` retrieval 不變式未被觸及，
  `make eval` 未跑的理由（gap 路徑不寫圖）成立。
- **範圍：** 沒有發現計畫外的順手重構、無關檔案改動、或未追蹤產物。diff 的 15 個檔案全部落在
  plan 的 approved path scope 內。`?v=20260810-1` 有依 CDN 快取規則同步 bump `app.js` 與 `styles.css`。
- **Rollback：** 無 migration、無新依賴，revert 這 15 個檔案即可；demo 資料靠 `make demo-reset` 復原。
  非 demo 資料見 L2。

## Unreviewed Areas and Residual Risk

- **未執行**：完整 `make test`、`make eval`、`make lint`(ruff/mypy)、`node --check`、任何瀏覽器操作。
  本次只獨立重跑了 `test_review_groups.py`（離線，20 passed）。
- **未驗證**：CI 實際狀態（無 `gh`）；owner 的 4/4 瀏覽器 pass 與其 Postgres 對照（採信報告）；
  「170 passed」這個數字；`make demo-reset` 的 live round trip。
- **未審**：`main` 上此變更以外的內容（PR #13/#14 的成果）、nginx/反向代理設定、
  `docs/expert-in-the-loop-plan.md` 與 roadmap 一致性。
- **殘餘風險**：主要集中在 M1（離線完整套件 + CI 無紀錄）與 L1（分類預設值汙染未來 backlog 統計）。
  兩者都不威脅 `status='approved'` 不變式，也不會讓未經核准的知識進入學生端 retrieval。
  找不到 findings 不等於正確 —— 前端行為與完整套件都在我的驗證半徑之外。

## Human Disposition Required

### 已裁決（owner，2026-08-10）

| 項目 | 決議 | 後續 |
|---|---|---|
| **M1** CI 綠燈無證據 | **CLOSED** —— owner 確認 CI 正確 | 無（記錄為人工確認，非機器驗證） |
| **L1** gap 下拉預設值 | **ACCEPTED，`unknown` 排第一** | **待實作** —— 走實作流程、開工作分支，**不由審查者執行** |
| **L2** gap 不可復原 | **選項 A** —— 現在不動 | 併入未來的 backlog 生命週期變更；有觸發條件（見 L2） |
| **L3** 旗標封鎖核准 | **選項 A** —— 維持現狀 | 有稽核的 engineer override 與 L2 一起設計 |

| **S1** 稽核 actor 恆為 `'demo'` | **選項 C** —— actor 由 admin key 決定 | **升格為獨立 Phase**，不在本次處理（見下） |

### S1 — 選項 C 的細節（獨立 Phase，本次不實作）

owner 決議（2026-08-10）：採選項 C，**但這不是一個 follow-up 小修，值得一個獨立 Phase**；
同時決定**暫不 seed 任何 admin key**（`.env` 未被修改，`ADMIN_API_KEYS` 維持現狀）。
審查者未執行任何相關變更，亦未觸碰任何憑證檔。

- **作法：** `routes_review.py` 目前以 `dependencies=[Depends(require_admin)]` **丟棄**了回傳值；
  作法：`routes_review.py` 目前以 `dependencies=[Depends(require_admin)]` **丟棄**了回傳值；
  改成 `actor: str = Depends(require_admin)`，把解析出的呼叫者名稱當成稽核 actor，
  **忽略 client 送來的 `reviewer`**。`require_admin`（`app/api/auth.py:35-45`）本來就回傳
  `vendor:key` 中的 vendor 名，docstring 明寫「so handlers/logs can attribute the action」——
  機制已存在、只是沒接上。無金鑰設定時退化為 `"anonymous"`，正好等於今天的本機 demo 狀態。
  明確**不採用**在前端加自由輸入姓名欄（看起來像身分驗證的假訊號）。

- **為什麼值得一個獨立 Phase（審查者提示，非決議）——三件必須一併處理的事：**
  1. **契約變更。** `ApproveRejectRequest.reviewer` / `SchemaGapRequest.reviewer` 的去留：actor 改由
     server 端決定後，`reviewer` 就是不可信欄位。要嘛移除（**破壞性契約變更**，需同步
     `api_contract.md` 與前端），要嘛降級為「顯示名稱」且明確不入稽核。本次新增的
     「空白 reviewer → 422」防線也會隨之失去意義。
  2. **測試面的連帶損害。** `ADMIN_API_KEYS` 一旦設定，`/admin` 即從開放翻為關閉；
     `backend/tests/` 目前有 **42 處**未帶 `X-API-Key` 直打 `/admin` 的呼叫，會全部變 401。
     必須同步處理（fixture 注入金鑰，或明確維持測試環境金鑰為空）。CI 以 `cp .env.example .env`
     起，若 example 維持空值則 CI 不受影響，但**本機 `make test` 會壞**。
  3. **上線姿態是安全決策。** 目前若 `ADMIN_API_KEYS` 為空，`biograph.busybutlazy.com` 的
     `/admin/*` 對外開放（任何人可核准／退回／記 gap，即改動知識圖譜）。設定金鑰同時是把這扇門
     關上，屬於獨立於 S1 的安全議題，應在同一個 Phase 內一起決定。另注意 `vendor:key` 的 vendor
     名會直接成為 `graph_change_logs.actor`，等同公開稽核欄位，命名須慎重；
     `scripts/manage_vendors.py` 自陳金鑰為明文儲存（demo-grade），選值時一併考量。

### 未裁決但非阻擋

L4（demo 腳本 UPDATE 條件不對稱／非交易）、L5（`reason` 無長度上限）、S2（文件 guard 順序）、
S3（孤兒 sample 檔）、S4（origin 上的 revert-14 分支）維持原判。

### 本報告產生的待辦（皆不由審查者執行）

| 待辦 | 型態 | 備註 |
|---|---|---|
| **L1** `GAP_OPTIONS` 把 `unknown` 排第一 + bump `app.js?v=` | 小修，一般實作流程 | 需開工作分支 |
| **S1-C** actor 由 admin key 決定 | **獨立 Phase** | 含契約變更、42 處測試調整、`/admin` 上線姿態決策 |

依 CLAUDE.md：**不得在 `main` 直接 commit**，需先開工作分支；非 trivial 變更須先產生
implementation plan 並取得人類批准。審查者不執行修正 —— 審查者修自己找出的 finding
等同自我核准。

### 審查者最終狀態聲明

本次審查對 repository 的唯一寫入是**本檔**（`changes/group-review-gap-outcome/REVIEW_REPORT.md`，
untracked，未 commit）。期間曾一度直接修改 `frontend/app.js` 與 `frontend/index.html`，
經 owner 指正後已完整撤銷（見 L1 處置）。工作區已核對為：除本檔外與合併後的 `main` 完全一致。
未修改任何憑證或設定檔（`.env` 未被讀取亦未被寫入）。唯一執行過的專案指令為容器內的唯讀複驗：
`docker compose run --rm -e OPENAI_API_KEY= backend pytest tests/integration/test_review_groups.py -q`
（20 passed）。

The reviewer does not approve, fix, merge, or release this change.

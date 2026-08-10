# Review Report: remediation round（`fix/review-remediation-gap-outcome`）

> **R1–R3 處置完成（2026-08-11，同分支）。** 執行者回覆:
>
> | 項目 | 處置 |
> |---|---|
> | **R1** 422 兩種 body 形狀 | **選項 B（owner 決議）** — `api_contract.md` 新增「已知例外」區塊,明列 Pydantic 層級驗證回 FastAPI 預設 `{"detail":[…]}`、無 `code` 欄位,並說明這是全站行為、統一需獨立變更。測試已依驗收條件強化:三個 verb 各斷言 **body 形狀**(422 有 `detail` 且無 `error`;上限內的 reason 走到 404 時斷言 `error.code == "not_found"`),不再只斷言 status code。 |
> | **R2** 交易邊界反轉了 failure path | **採 B1** — Neo4j 刪除迴圈移到交易**外**:先刪圖並收集已刪項目,再於單一 PG 交易內寫稽核 + 翻狀態 + `_reset_schema_gaps`。最壞情況由「圖已改但無稽核」翻轉為「刪除已記錄、狀態未重置」,重跑即收斂。未引入任何跨 store 補償機制。 |
> | **R3** S4 敘述失準 | **已更正** — `REVIEW_REPORT.md` 的 S4 列改為「**RESOLVED —— 該分支已被刪除**」,並記錄先前「NOT REPRODUCIBLE」的錯誤與更正理由。執行者另行核實 `git cat-file -t 87229e4` → `commit`,該 object 仍在本地 store,可獨立佐證該 ref 曾經存在。 |
> | 其他觀察:L1 註解宣稱過強 | **已收回** — 程式註解改寫為「稽核紀錄無法佐證此點(demo 群組本來就真的是 permissive effect,帶著預設與刻意選對無法區分)——而這正是問題本身」;`REVIEW_REPORT.md` 亦記錄 commit `2a72bdf` 訊息含此過度宣稱。 |
> | 其他觀察:propose 側無上限 / 無獨立 plan | 依複檢指示**不處理**,維持記錄。 |
>
> 完成後驗證(全部離線姿態,全新容器):`pytest tests ingestion/tests` → **171 passed**;
> `app.eval.runner` → Recall@5 1.0 / Grounded 1.0 / P95 168.6ms / **Overall PASS**;
> ruff check + format → 全清 / 99 files;mypy → 77 files clean;`node --check` OK。
> `make demo-reset` live round trip(**刻意先核准一組製造 approved 資料**,讓 Neo4j 刪除那條路徑
> 真的被走到)→ `{'reset_items': 2, 'graph_deleted': {'nodes': 1, 'edges': 1},
> 'reset_schema_gap_groups': 1}`,兩個群組都回到佇列,稽核鏈 approve → schema_gap → delete/reset 完整。
>
> 下方原始複檢內容保持不動。

> **給執行者的說明**：這是對 remediation 分支的第二輪獨立審查。上半部是**已完成的複驗**
> （你不需要重跑），下半部 R1–R3 是**新發現、待處置**的項目。完整脈絡見同目錄
> `REVIEW_REPORT.md` §Remediation Verification（內容相同，此檔為可直接執行的精簡版）。
>
> **邊界**：審查者不修改實作。本檔只描述問題與有界的修正方向，不代表已批准施工——
> R1 需要 owner 先做一個決定（見該節）。

## 1. 審查範圍

- 分支：`fix/review-remediation-gap-outcome` @ `2a72bdf`（單一 commit）
- 比較基準：`main` @ `6d855c0`；`main...HEAD` = 9 檔 +442/−51
- 變更檔案：`backend/app/schemas/curation.py`、`backend/tests/api/test_review.py`、
  `frontend/app.js`、`frontend/index.html`、`scripts/reset_demo_review.py`、
  `docs/api_contract.md`、`docs/expert-in-the-loop-plan.md`、
  `changes/group-review-gap-outcome/{REVIEW_REPORT,VERIFICATION_REPORT}.md`
- 獨立性：複驗者未參與 remediation 的規劃或實作，未修改任何實作檔。

## 2. 判定：宣稱屬實，不需重做

第一輪 findings 的處置（M1／L1／L2／L3／L4／L5／S2／S3／S4）**全部核實通過**，S1 依 owner 指示
排除。證據等級已從「人工口頭確認」升級為「機器可複現」。複驗者實跑結果：

| 檢查 | 結果 |
|---|---|
| `pytest tests ingestion/tests -q`（離線 `-e OPENAI_API_KEY=`） | **171 passed in 73.64s** |
| `python -m app.eval.runner`（離線） | Recall@5 **1.0**／Grounded **1.0**／P95 205.2ms／**Overall PASS** |
| ruff 0.15.21 `check` / `format --check` | All checks passed／99 files already formatted |
| `mypy backend/app ingestion scripts` | Success: no issues found in 77 source files |
| `node --check frontend/app.js` | OK |
| `git ls-remote --heads origin` | 只有 `main`、`feat/two-gate-review-p4`、本分支（S4 已解決） |
| Postgres 狀態查核 | `proposed_by='demo'` 19 筆／5 群組全為 `proposed`（demo-reset round trip 成立） |

**執行者不需要重跑上表。** 以下三項才是待辦。

---

## 3. R1（Low）— L5 的 422 脫離了本端點文件化的錯誤契約

**位置**：`backend/app/main.py`（缺 handler）／`backend/app/schemas/curation.py`（新增的
`Field(max_length=…)`）／`backend/tests/api/test_review.py::test_oversized_reason_and_reviewer_are_422_on_every_group_endpoint`

**證據**（全新容器實測，非推論）：

```
POST /admin/review/groups/group:does_not_exist/gap
  reason = "字"*2001        → 422 {"detail":[{"type":"string_too_long","loc":["body","reason"],...}]}
  schema_gap_type = "bogus" → 422 {"error":{"code":"invalid_request","message":"invalid schema_gap_type: 'bogus'"}}
```

**重現**：
```
docker compose run --rm -T -e OPENAI_API_KEY= backend python -c "
from fastapi.testclient import TestClient; from app.main import app
c=TestClient(app); u='/admin/review/groups/group:does_not_exist/gap'
print(c.post(u, json={'reviewer':'t','reason':'字'*2001,'schema_gap_type':'unknown'}).text[:200])"
```

**違反的要求**：`docs/api_contract.md:256` 對這三個群組端點明寫「錯誤 body 遵循
`{"error": {"code", "message"}}`」；gap 端點的四道防線表格亦標示 `422 invalid_request`。
`main.py` 只註冊了 `APIError` 與 `Exception` 兩個 exception handler，**沒有
`RequestValidationError` handler**，故 Pydantic 層級的驗證走 FastAPI 預設格式。

**影響**：同一端點的同一狀態碼出現兩種 body 形狀，其中一種沒有 `code` 欄位；依 `error.code`
分支的消費端會拿到 `undefined`。前端 `apiError` 的 `formatDetail` 有處理 `detail` 陣列，UI 不會
壞，但會在中文介面顯示英文的「reason：String should have at most 2000 characters」。
現有測試只斷言 `status_code == 422`，**不會攔截到這件事**。

**⚠ 需要 owner 先決定（執行者不要自行選）**：

| 選項 | 做法 | 影響範圍 | 代價 |
|---|---|---|---|
| **A（一致性優先）** | 在 `main.py` 加 `RequestValidationError` handler，轉成 `{"error":{"code":"invalid_request","message":…}}` | **全站所有 422**（含 `/query`、`/check-answer`、ingest 等既有端點） | 跨端點契約變更，需檢查所有既有 422 測試與前端 `formatDetail` 路徑；可能牽動 `docs/api_contract.md` 多節 |
| **B（範圍最小）** | 不改行為，只在 `api_contract.md` 明列「Pydantic 層級驗證回 FastAPI 預設 `{"detail":[…]}`」這個例外 | 只有文件 | 契約留下一個已知例外，但至少是**明說的** |

審查者傾向 **B**：A 是正確方向，但它是全站契約決策，不該夾在一次 finding remediation 裡做；
若要做 A，應獨立成一個 change（含全站 422 盤點）。

**驗收條件（無論 A 或 B）**：新增或修改的測試必須斷言 **body 形狀**，不能只斷言 status code。

---

## 4. R2（Low）— L4 的交易邊界被擴大，failure path 的性質被反轉

**位置**：`scripts/reset_demo_review.py::reset()`

**問題**：原 L4 finding 只指出 `_reset_schema_gaps` 內「稽核 INSERT + 狀態 UPDATE」這組
**純 Postgres** 操作不對稱。remediation 把 `reset()` **整段**包進 `async with pg.transaction()`，
使 Neo4j 的 `DETACH DELETE` 迴圈與 `_audit_delete` 都落在同一個交易內——這超出該 finding 的範圍。

**性質變化**：

| | 失敗態 | 稽核紀錄是否誠實 |
|---|---|---|
| 舊行為 | 稽核列已寫、狀態未翻 | ✅ 記錄了真的發生過的刪除 |
| 新行為 | Neo4j 已刪、稽核列被 rollback | ❌ **圖被改動卻沒有稽核紀錄** |

對一個以 append-only 稽核為主軸的專案，這是最不該出現的形狀。

**為何仍只評 Low**（執行者請一併理解，不要過度反應）：
1. 這是 demo 腳本（`make demo-reset`），不在 production 或學生端路徑；
2. 程式碼註解**已預見**此限制（"that cross-store limit is inherent … a re-run completes the job"），
   且該推論成立——rollback 後項目仍是 `approved`，重跑會重新刪（冪等）、重新寫稽核列後 commit，
   最終狀態與稽核都會正確。殘留風險僅限「失敗後從未重跑」的窗口。
3. 次要副作用：交易在跨 store 網路 I/O 期間持續持有列鎖。

**有界的修正方向（二選一，執行者可自行判斷）**：
- **B1**：把 Neo4j 刪除迴圈移到交易**外**（先刪圖，再於單一 PG 交易內寫稽核 + 翻狀態）。
  這同時滿足原 L4（PG 側原子）與 R2（不會 rollback 掉已發生刪除的稽核）。
- **B2**：維持現狀，把「失敗後必須重跑」從註解升格為腳本輸出的明確操作要求（例如失敗時
  print 一行指示）。

**不要做**：不要為此引入跨 store 的兩階段提交或補償交易機制——demo 腳本不值得。

---

## 5. R3（記錄準確性，非程式碼問題）— S4 的敘述需更正

**位置**：`changes/group-review-gap-outcome/REVIEW_REPORT.md` 檔頭 remediation 表格的 S4 列。

**問題**：該列寫「**NOT REPRODUCIBLE**」，隱含第一輪 finding 從未成立。事實是：該分支在
**2026-08-10 審查當下確實存在**——原始依據是當時 `git branch -a` 輸出中的
`remotes/origin/revert-14-chore/repo-ci-hardening`（commit `87229e4 Revert "chore: harden
repository ignores and CI"`，基底 `da2eed2`，不含 PR #15）。2026-08-11 已無此 ref，
本地 remote-tracking ref 亦被 prune。

**修正方向**：把該列敘述改為「**已解決 —— 該分支已被刪除**」，其餘（`main` 無 Revert commit、
`.dockerignore` 與 CI 硬化完好）維持。結論（關閉此項）不變。

**為什麼值得改**：「finding 從未成立」與「finding 成立且已被處理」在稽核紀錄上意義不同。
這份文件本身就是治理證據，不該把後者寫成前者。

---

## 6. 明確的非目標（執行者請勿擴大範圍）

- **S1**（稽核 `actor` 恆為 `'demo'`）—— owner 已決議為獨立 Phase，**本輪不處理**。
- **L3**（旗標封鎖核准）—— owner 決議選項 A，維持現狀，**不要動**。
- **L2**（gap 不可復原）—— owner 決議選項 A，已文件化，**程式碼不要動**。
- 不要順手重構 `reset_demo_review.py` 的其他部分、不要改 `approve_group`/`reject_group`/
  `record_group_gap` 的任何邏輯、不要動 `GAP_OPTIONS` 的分類文字（那是 owner 領域用語）。
- `CurationGroupCreate.reason` / `CurationItemCreate.reason`（propose 側）仍無長度上限——
  這是**已知且刻意**的範圍外項目（原 finding 只涵蓋三個 dispose 端點），**本輪不要順手補**；
  若要做，併入 R1 選項 A 的全站盤點。

## 7. 完成後的驗證要求

```
docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q   # 需 ≥171 passed
docker compose run --rm -e OPENAI_API_KEY= backend python -m app.eval.runner         # 需 Overall PASS
docker run --rm -v "$PWD":/io -w /io ghcr.io/astral-sh/ruff:0.15.21 check backend/app ingestion backend/tests ingestion/tests scripts
docker run --rm -v "$PWD":/io -w /io ghcr.io/astral-sh/ruff:0.15.21 format --check backend/app ingestion backend/tests ingestion/tests scripts
mypy backend/app ingestion scripts
node --check frontend/app.js        # 若動到前端才需要
```

若動到 `scripts/reset_demo_review.py`，額外做一次 `make demo-reset` live round trip 並記錄輸出。

## 8. 環境事實（非缺陷，但會誤導驗證）

運行中的 `backend` 容器啟動於 `2026-08-10T14:57:59Z`，早於 remediation 的檔案修改時間，且
`backend/Dockerfile` 的 uvicorn **沒有 `--reload`**。因此透過 `http://localhost:8080`
（以及公開網域）打到的是**容器啟動當下的舊碼**。

- 複驗者最初對 R1 的 live 探測回了 `404` 而非 `422`，就是踩到這一點；改用
  `docker compose run --rm backend …` 的全新容器後才得到正確結果。
- **執行者請注意**：任何 live HTTP 驗證都必須先 `docker compose up -d backend`，
  否則會驗到舊碼並得到錯誤結論。
- 本分支尚未合併，公開網域目前仍是 pre-remediation 的行為。

---

**審查者不核准、不修正、不合併、不發布本變更。** R1 需 owner 先在 A／B 之間做決定，
R2／R3 可由執行者直接依上述有界方向處理。

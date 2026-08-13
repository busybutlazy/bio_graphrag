# Verification Report: ingest-concurrency-guard

- **Plan revision**: 1(Approved / jett / 2026-08-13,medium / `supervised-auto`)
- **分支**:`feat/ingest-concurrency-guard`,自 `main` @ `57d721e`。**未 commit、未 push。**
- **驗證模式**:evidence-only —— 未修改任何實作邏輯。
- **總結**:**PASS(第二輪)**。
  第一輪停在 `ruff format --check`(見 §3),依 stop condition 停止並回報;
  jett 於 2026-08-13 批准執行 `ruff format` 後重跑,三項 lint 與全套測試皆通過。

---

## 1. 驗收條件對照

| AC | 內容 | 實作 | 測試 | 結果 |
|---|---|---|---|---|
| AC1 | 同來源第二次抽取在花錢前被擋,`extract_fn` 呼叫 0 次,不新增 job 列 | `load_postgres.claim_ingest_source`、`runner.py:251` | `test_claim_refuses_a_second_extraction_of_the_same_source`、`test_a_second_ingest_of_the_same_source_spends_nothing` | ✅ |
| AC2 | `POST /admin/ingest/run` 回 409 `ingest_already_running`,訊息含 job_id 與開始時間 | `routes_ingest.ingest_run` | `test_run_refuses_a_second_ingest_of_the_same_source` | ✅ |
| AC3 | 不同來源不受影響 | 索引以 `source_path` 為鍵 | `test_claim_allows_a_different_source` | ✅ |
| AC4 | `success` 與 `failed` 兩種收尾都釋放來源 | 索引述詞限 `status='running'` | `test_claim_reuses_the_source_once_the_job_is_finished` | ✅ |
| AC5 | 預覽/dry-run 永不被擋,也不建立 job 列 | `runner.py` dry-run 分支在宣告之前 return | `test_preview_is_never_blocked` | ✅ |
| AC6 | seed 路徑不變,連續兩次成功 | 索引述詞限 `job_id LIKE 'ingest:%'` | `test_the_seed_pipeline_is_not_covered_by_the_guard` + `make seed` ×2 | ✅ |
| AC7 | 逾時孤兒不擋新 job,被標 `failed` 且留下原因 | `claim_ingest_source` 的前置 UPDATE | `test_claim_takes_over_a_stale_orphan` | ✅ |
| AC8 | 無迴歸,測試數 ≥ 基準 + 新增數 | — | 見 §2 | ✅ |

**AC7 的反向**(plan 未要求,但不驗就等於沒守住 `STALE_AFTER` 偏長這個取捨):
`test_a_job_just_short_of_stale_still_blocks` —— 差一分鐘未到門檻的 job 仍然擋。✅

## 2. 執行的命令與結果

| # | 命令 | 結果 | Exit |
|---|---|---|---|
| 1 | `docker compose build backend` | Image built | 0 |
| 2 | `docker compose up -d backend` | Started | 0 |
| 3 | `bash scripts/wait_for_services.sh localhost 8080 240` | All dependencies healthy | 0 |
| 4 | `make health` | 全部 `"ok": true` | 0 |
| 5 | `docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q` | **1 failed, 241 passed in 88.00s** | 1 |
| 6 | `make eval` | 見 §4 —— 第一次 FAIL(延遲)、第二次 PASS | 1 → 0 |
| 7 | `make seed` ×2 | 兩次皆 `status: success`,nodes 45 / edges 84 / chunks 9 | 0, 0 |
| 8 | `ruff check` + `ruff format --check` + `mypy`(拋棄式容器) | **`ruff format --check` 失敗** | 1 |

**#2 本身就是一項證據**:backend 在**非空的既有 DB** 上重啟成功,代表含正規化 UPDATE 與
`CREATE UNIQUE INDEX` 的新 migration 在 `ensure_schema` 中跑得過——Plan R5 點名的最大自傷風險
(migration 失敗 → 後端起不來)未發生。

**#5 的唯一失敗是既有 flake**:`ingestion/tests/test_pipeline.py::test_pipeline_run_is_idempotent`
`assert 12 == 9`,與本次實作前取得的基準(1 failed, 232 passed)**逐字相同**,
成因是 volume 非乾淨(`docs/handoff-2026-08-12.md` 陷阱 5)。**非迴歸。**
241 = 232 基準 + 9 個新測試(8 個在 `test_document_ingest.py`、1 個在 `test_ingest.py`)。

## 3. 驗證失敗的項目(停止原因)

`ruff format --check` 在 `ingestion/tests/test_document_ingest.py` 失敗,
`1 file would be reformatted, 106 files already formatted`。內容為 3 處

```python
assert await pg_conn.fetchval(...) == 1
```

需要 ruff 的斷行括號化(`assert (await ... == 1)`)。**純格式,無行為改變**,
但 CI 會擋——`ruff check` 通過不代表 `ruff format --check` 通過(陷阱 9)。

**當下未執行 `ruff format`**:`run-approved-change` 禁止由驗證階段切回實作,
Plan 的 mandatory stop conditions 也列了「完整驗證失敗」。修法是一行命令,但需要人類裁示。

### 3.1 解除(2026-08-13,jett 批准後)

| # | 命令 | 結果 | Exit |
|---|---|---|---|
| 8a | `ruff format ingestion/tests/test_document_ingest.py` | 3 處 assert 括號化,+11 行,**無行為改變** | 0 |
| 8b | `ruff check` + `ruff format --check` + `mypy`(拋棄式容器) | `All checks passed!` / `107 files already formatted` / `Success: no issues found in 83 source files` | 0 |
| 8c | `docker compose build backend` + 全套離線測試重跑 | **1 failed, 241 passed in 89.47s**(同一個已知 flake) | 1 |

**`make eval` 未重跑**,這是刻意的:格式化不可能影響檢索或作答,而重跑要再花一次真實 token
(§5)。代價是本輪沒有 eval 的新證據,沿用 §4 那次 `passed=True` 的結果。

第一次執行 `ruff format` 時在拋棄式容器內以 root 身分跑,寫 `.ruff_cache` 時因該目錄
(既有、gitignored、root 所有)權限不足而報錯——**但檔案在那之前已經被改好**,
所以第二次以一般使用者身分跑時回報 `1 file left unchanged`。兩次的產物相同,無殘留。

## 4. `make eval` 的兩次結果(需要說明,否則會被誤讀)

| run_id | mode | recall@5 | grounded | P95 | passed |
|---|---|---|---|---|---|
| `eval:9edfab33…` | openai | 1.0 | 1.0 | **6366.0 ms**(門檻 5000) | **False** |
| `eval:eee9a3f3…` | openai | 1.0 | 1.0 | 3750.4 ms | True |

第一次失敗**只因延遲 P95 超標**,recall 與 grounded 皆滿分。第二次同樣的 22 題全過。
本變更未觸及任何檢索或作答路徑(`/query` 與 `app/rag/*` 皆未改動),
成因是 Raspberry Pi 上走 OpenAI 網路往返的抖動。**判定為環境抖動,非迴歸**——
但「重跑一次就過」是弱證據,如需硬證據應在乾淨 CI runner 上重跑。

## 5. 對自己不利的揭露:`make eval` 花了真實 token

**Plan〈Verification Strategy〉第 8 條寫「本變更的 token 預算為 0」,這一點沒有做到。**
`make eval` 沒有離線化(`docker compose run --rm backend python -m app.eval.runner`,
未帶 `-e OPENAI_API_KEY=`),因此讀到 `.env` 的金鑰、**以 `mode=openai` 執行了兩次**,
22 題 × 2 = 44 次真實作答。

- Plan 同時把 `make eval` 列為必要驗證、又宣稱 token 預算為 0,**這兩條互相矛盾,規劃時未察覺**。
- **實際花費未被記錄**:eval runner 不寫 `query_logs`,`app/eval/runner.py` 與
  `app/rag/pipeline.py` 都沒有累計 token。因此**無法給出實測數字**;
  以 gpt-4o-mini 級別、每題約 1–2k tokens 粗估為 5 萬–10 萬 tokens 量級,
  **這是估算,不是量測**。
- 第二次執行是為了釐清第一次的非零退出碼。若當時先查 `evaluation_runs` 表
  (最終正是這樣查出真因的),**這次重跑可以避免**。

沒有其他花費 token 的路徑被執行:全套測試皆帶 `-e OPENAI_API_KEY=`,
且未執行任何真實抽取(`POST /admin/ingest/run` 一次都沒有真的跑過)。

## 6. 未驗證與已知限制

- **未在乾淨 volume 上驗證**。既有 flake 與 eval 延遲抖動都源於此;CI 從乾淨 runner 起跑才是硬證據。
- **未驗證「其他機器的既有 volume 上已有重複 running 列」的情境**(Plan R5 的未知)。
  本機實測為 0 列,正規化 UPDATE 是 no-op;它在非 0 情況下的行為只由 SQL 邏輯保證,**沒有測試覆蓋**。
- **未做真實併發壓測**。測試以「先造出一列 running,再提交第二次」模擬,
  而非兩個真的同時起跑的 job。索引的原子性由 Postgres 保證,但**這條路徑沒有被真正的競態驗證過**。
- **孤兒 2 小時門檻沒有端到端驗證**,只有以 `started_at` 回推時間的單元測試。
- **前端未被驗證**。409 依賴 `frontend/app.js` 的 `apiError` 泛用顯示 `error.message`;
  這是讀碼推論,**沒有人眼看過真實渲染**,倉庫也沒有前端測試設施(與 N1 遺留的 T6 同一個缺口)。
- **`make eval` 的 openai 模式在 CI 上是否成立未查證**。若 CI 也帶金鑰,延遲門檻的抖動會是 CI 的既有風險,
  但那不屬本變更範圍。

## 7. 結論

8 條驗收條件全數以測試證據通過,無迴歸,三項 lint 通過。**完整驗證 PASS。**

一項偏差已揭露且未被合理化:§5 的 `make eval` token 花費——
plan 宣稱零花費卻把 `make eval` 列為必要驗證,是**規劃階段的矛盾**,
事後批准修格式並不改變「當時多花了兩輪 eval」這個事實。

**未執行的事項**:push、獨立審查、人類驗收。commit 已由 jett 於 2026-08-13 明確授權
(僅 commit,不含 push)。

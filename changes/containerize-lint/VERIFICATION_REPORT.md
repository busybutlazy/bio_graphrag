# Verification Report: containerize-lint

- **Plan revision**：1（Approved / jett / 2026-08-14，low / `supervised-auto`）
- **Diff base**：用 `git merge-base main HEAD` 取，**不要寫死 SHA**——本分支已 rebase 過一次，
  原本寫的 `b71481f` 已失效（審查 M2）。複核用 `git diff main...HEAD`（三點）。
  rev 1 的驗證是在 commit 前於工作區狀態下執行，該狀態原封不動進了本分支的 commit。
- **姿態**：全部命令在 Docker 內執行；host **未安裝任何套件**（host 至今仍無 `ruff`）
- **結論**：**AC1–AC7、AC9 通過；AC8 未達字面標準**。清空 volume 重跑後
  `1 failed, 241 passed`：原本的兩個失敗**皆轉綠**，剩下的一個
  （`test_qdrant_payload_is_queryable`）已完整歸因為「本機 `.env` 有 OpenAI key ＋ 測試硬編集合名」
  的既有不一致，與本變更的 diff 無交集，且 CI（無 key）不受影響。詳見 §AC8。

## 環境

- 主機：Raspberry Pi（`Linux 6.12.62+rpt-rpi-v8`），Docker Compose v5.1.0
- lint 映像：`bio_graphrag-lint`，`python:3.12-slim` + `backend/requirements-dev.txt`
  （`ruff==0.15.21`、`mypy==1.19.1`），**未裝 runtime 依賴**（D1 = A）
- 無 mock、無 stub；`make test` 依專案設計在離線模式（無 `OPENAI_API_KEY`）執行

## 需求 → 實作 → 證據

| AC | 需求 | 實作 | 命令 | 結果 |
|---|---|---|---|---|
| AC1 | host 無 ruff 時 `make lint` 可完整跑完 | `scripts/lint.sh` + compose `lint` service + Makefile | `which ruff`（無）→ `make lint` | **PASS** exit 0：`All checks passed!` / `107 files already formatted` / `Success: no issues found in 83 source files` |
| AC2 | 負向對照：真的會紅 | — | 見下方 §負向對照 | **PASS**（兩項皆 exit 2） |
| AC3 | 不新增 root-owned 檔案；既存快取已清 | `RUFF_CACHE_DIR`/`MYPY_CACHE_DIR` → `/tmp`；`user:` 帶真實 uid/gid | `find . -user root -mmin -4`（lint 執行窗口）；`ls -ld .ruff_cache .mypy_cache` | **PASS**：lint 窗口內無任何 root-owned 新增；兩個快取目錄已不存在 |
| AC4 | `make format` 改寫的檔案 owner 不變 | 同上 | `make format` 後 `ls -l` | **PASS**：`-rw-rw-r-- jett jett` |
| AC5 | `up` 不啟動 lint；compose 設定合法 | `profiles: ["tools"]` | `docker compose config --quiet`；`docker compose config --services` | **PASS**：exit 0；服務清單為 `postgres qdrant neo4j backend nginx`，**不含 lint** |
| AC6 | CI 不再裝 host 套件 | `.github/workflows/ci.yml` | — | **PASS（靜態）／未實跑**：兩個 step 已移除，保留 `checkout` + `make lint`。**GitHub Actions 未執行，結果須於 PR 觀察** |
| AC7 | 命令與路徑只有一處定義 | `scripts/lint.sh` | `grep -n 'ruff\|mypy' Makefile docker-compose.yml .github/workflows/ci.yml` | **PASS**：命中 4 處全為註解或快取路徑環境變數，**無任何命令或路徑清單** |
| AC8 | `make test` 仍通過 | 未動 runtime 映像內容 | `make test` | **見 §AC8** |
| AC9 | 文件同步 | `CLAUDE.md`、`Makefile` 註解、`docs/notes.md` N10 | `git diff` | **PASS** |

## 負向對照（AC2，依 `docs/notes.md` N11 的要求）

守門指令必須證明「缺陷存在時它會失敗」，否則綠燈不具鑑別力。

| 人為缺陷 | 位置 | `make lint` | 證據 |
|---|---|---|---|
| unused import（ruff F401） | 暫存檔 `scripts/_lint_negative_control.py` | **exit 2** | `Found 1 error.` + `help: Remove unused import: json` |
| 回傳型別不符（mypy `[return-value]`） | 同上 | **exit 2** | ruff 兩項綠 → `error: Incompatible return value type (got "str", expected "int")`；`Found 1 error in 1 file (checked 84 source files)` |

第二項同時證明**第三個命令真的會執行**（若 script 在 ruff 之後就結束，mypy 的錯永遠不會被看到）。
暫存檔已刪除，刪除後 `make lint` 回到 exit 0（`83 source files`、`107 files already formatted`，
與加入暫存檔前的計數一致）。

## AC8 — `make test`（兩輪：現地 volume → 全新 volume）

### 第二輪（決定性）：清空 volume 後重跑

依人類指示（2026-08-14）執行 `docker compose down -v` → `make up` → `make seed` → `make test`。
清除前先把 seed 未收錄的三張表 dump 到 session scratchpad（`curation_items` 20 列 `proposed`、
`graph_change_logs` 24 列、`ingestion_jobs` 208 列）；人類已在知情下裁定開發階段可清除。
`make seed` 回填 45 nodes / 84 edges / 5 documents / 9 chunks 與 5 個 demo review groups。

結果：**`1 failed, 241 passed in 293.92s`**

- ✅ `test_pipeline_run_is_idempotent` — **轉綠**。證實第一輪的失敗確為 volume 資料狀態，與本變更無關。
- ✅ `test_evaluation_meets_thresholds` — **轉綠**。證實為整套同跑時的延遲門檻假失敗。
- ❌ `ingestion/tests/test_pipeline.py::test_qdrant_payload_is_queryable` — **新暴露的既有缺陷**
  （非 flaky：單獨重跑 0.40 秒內穩定失敗）。

### 對 `test_qdrant_payload_is_queryable` 的歸因（證據鏈完整）

- 測試逐字讀 `load_qdrant.COLLECTION_NAME`（＝`biology_chunks`）。
- 但 `load_qdrant.py:25` 的集合名**取決於向量維度**：
  `return COLLECTION_NAME if dim == 128 else f"{COLLECTION_NAME}_{dim}"`。
- 本機 `.env` 有 OpenAI key → embedding 維度 1536 → 資料實際寫進 `biology_chunks_1536`。
- 實測（`curl localhost:6333/collections/...`）：
  - `biology_chunks`（dim 128）→ **points_count = 0**
  - `biology_chunks_1536`（dim 1536）→ **points_count = 9**
- 先前之所以會過，是因為舊 volume 裡還留著更早期無 key（dim 128）時寫入的點；volume 一清就露餡。
- **CI 不受影響**：CI 以 `.env.example`（無 key）啟動 → dim 128 → 寫入 `biology_chunks` → 測試會過。

因此：**此失敗是本機環境（有 key）與測試硬編集合名的既有不一致，與 `containerize-lint` 的 diff
無任何交集**（本變更未觸碰 `ingestion/`、未改 runtime 映像內容）。
依 `run-approved-change` 的規則，**未在驗證階段修它**。

### 附帶發現（不在本變更範圍，建議另立 backlog）

`make test` 在本機是**帶著 OpenAI key 跑的**（backend service 走 `env_file: .env`），
與 `CLAUDE.md` 所寫的「tests run offline (no key configured)」不符——意味著本機跑測試**可能真的在花 token**。
這與記憶中「`make eval` 本機會花錢」是同一個根因。**本次未處置**。

### 第一輪（清除前，保留紀錄）

`make test` → **exit 2**，`2 failed, 240 passed in 331.43s`。

**1. `ingestion/tests/test_pipeline.py::test_pipeline_run_is_idempotent`**
- 斷言：`assert chunk_count == len(chunks)` → `assert 12 == 9`
- 歸因證據：`select doc_id, count(*) from chunks group by doc_id` 顯示 DB 內含
  `doc:private:endocrine_demo_v1`（**4 列**），這是先前真實章節抽取留下的資料，
  不屬 seed 來源。失敗原因是 **Postgres volume 非全新**，與建置設定無關。
- 此項**已於 plan 的 Verification Strategy 事先列為已知基線雜訊**。

**2. `tests/integration/test_evaluation.py::test_evaluation_meets_thresholds`**
- **未事先列入基線**（本報告的揭露缺口，非事後合理化）。
- 歸因證據：緊接著單獨重跑 `docker compose run --rm backend pytest tests/integration/test_evaluation.py -x`
  → **3 passed in 120.81s**。同一份程式碼、同一個映像，單獨跑就綠，
  與「Pi 上整套測試同時跑時延遲門檻假失敗」的已知現象一致。
- **未取得** 本變更前的同一次全套執行結果作為對照（見〈未支持的宣稱〉）。

**共同的結構性論據**：本變更的 diff 不含任何 `backend/app/` 或 `ingestion/` 下的程式；
`backend/Dockerfile` 的 runtime stage 內容一行未改（只加 `AS runtime` 標籤），
並已用 `docker image inspect`（`Cmd`、`WorkingDir` 不變）與容器內 `import fastapi` 驗證預設建置目標未變。

## 未執行 / 未支持的宣稱

- **CI 未實跑**：`.github/workflows/ci.yml` 的改動只有靜態證據。ubuntu-latest runner 內建 Docker
  的假設未經本次驗證；`LINT_UID`/`LINT_GID` 在 runner（uid 非 1000）上的行為**未實測**（plan R2）。
- **未取得 `b71481f`（變更前）的 `make test` 全套對照**：三個失敗的「既有」屬性靠歸因證據支持
  （清空 volume 後兩個轉綠、第三個以 Qdrant 集合實測點數定位到 `.env` 的 key、
  以及 diff 不含任何 runtime 程式），**不是靠在 baseline commit 上實跑一次對照**。
- **未驗證跨機器**：只在本機一台 Pi 上執行。
- `scripts/__pycache__`、`backend/app/**/__pycache__` 等仍為 root 所有——由 `make test` 的 backend
  容器寫入，**既有行為，不在本變更範圍**，AC3 只宣稱 lint／format 路徑不產生 root-owned 檔案。

## 風險

- 首次 `make lint` 需 build（本機實測 **2m50s**，多數花在 Pi 上 unpack 映像層）；之後暖機
  **3.0s–26.5s 不等**——Pi 的負載差異很大（審查者在另一時段量到 22.8s，rev 2 量到 24.6s／26.5s），
  **不要把單一數字當成基準**。rev 2 起每次多一個 `--build`（無變動時約 +2–3 秒）。
  CI 每次都是冷啟動，lint job 會比原本的 `pip install`（有 pip cache）慢，**未量測**。
- 掛載 repo 根使 lint 容器看得到 `.env` 與 `data/seed/`。該容器不連任何服務、只跑 ruff/mypy。

## 偏差

- **快取刪除方式**：`rm -rf` 在 host 因 root 所有而失敗（plan 的 sudo stop condition）。
  未用 `sudo`，改以 `docker compose run --rm --user 0:0 --entrypoint sh lint -c 'rm -rf ...'` 完成。
  詳見 `TASK_LOG.md` T6。審查列為 M3；**人類（jett，2026-08-14）裁定接受本次，且不另立規則。**

---

# Rev 2 驗證（審查處置 R1–R6）

- **姿態**：同 rev 1，全部容器內執行。**未重跑 `make test`**：rev 2 未觸碰任何 runtime 程式
  （改動限於 `Makefile`、`docker-compose.yml`、`backend/requirements-dev.txt` 的註解與報告）。

| 任務 | 命令 | 結果 |
|---|---|---|
| **R1** `--build` 真的會重建 | 改動 `backend/requirements-dev.txt`（R4）後 `make lint` | **PASS**：輸出含 `Image bio_graphrag-lint Built`（pip 層失效重跑，2m25s），三項檢查仍綠。**這正是審查 M1 描述的情境：修正前此處不會有任何 build 步驟** |
| **R1** 穩態成本 | 無改動時 `make lint` | **26.5s**（同機同時段的無 `--build` 對照為 24.6s）→ 額外成本約 **2–3 秒** |
| **R5** backend 建置目標明確化 | `docker compose build backend`；`docker image inspect` | **PASS**：`Cmd=["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]`、`WorkingDir=/app`——仍是 runtime stage |
| **R5** compose 合法性 | `docker compose config --quiet` | **PASS** exit 0 |
| **R4** lint 仍全綠 | 同 R1 的 `make lint` | **PASS**：`All checks passed!` / `107 files already formatted` / `Success: no issues found in 83 source files` |
| **R6** dump 已持久化 | `cp` → `wc -l` | **PASS**：`~/backups/bio_graphrag/2026-08-14-pre-wipe-governance-tables.sql`，302 行 / 131 KB（與審查者查到的行數一致） |

**rev 2 未做的驗證**：CI 仍未實跑（AC6 的缺口不變）；`make format` 未重跑（審查 AC4 同此判斷）；
未跨機器。**rev 2 本身尚未經獨立審查。**

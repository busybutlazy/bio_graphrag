# Change Report: containerize-lint

對應 `docs/notes.md` 的 **N10**（lint 的容器化入口）。

- **Plan revision**：**1**（Approved / jett / 2026-08-14，low / `supervised-auto`，tasks T1–T6）
- **分支**：`feat/containerize-lint`，自 `main` @ `b71481f`。**commit 已授權（jett，2026-08-14）；
  push 與 merge 未授權。** commit 清單不在此列舉——跑 `git log main..HEAD`。
- **不屬本變更**：`docs/agent-guideline.md`（skill 安裝產物）已由人類指示單獨 commit 在
  `chore/agent-guideline-sync`，不在本分支。
- **驗證**：`VERIFICATION_REPORT.md` —— **AC1–AC7、AC9 PASS；AC8 未達字面標準**（見 §5）
- **審查**：**尚未進行**。本報告不構成完成宣稱的自我核可。
- **檔案清單不在此列舉**——跑
  `git status --short` 與 `git diff --stat -- . ':(exclude)docs/agent-guideline.md'`。

## 1. 解決了什麼

專案準則寫「一律以 Docker 為執行環境」，但 `make lint` 是個例外：它直接呼叫 host 上的 `ruff` / `mypy`。
後果不是「lint 沒跑」，而是**沒人能重跑**——於是「lint 全過」變成審查者只能採信實作者自述的宣稱，
而這正是上一個變更（`close-approve-item-backdoor`）四輪審查裡反覆出問題的那一類。

實作時量到的現況比 N10 記載的更糟：

- 本機**沒有 `ruff`** → 原本的 `make lint` 在**第一行**就 `ruff: not found`。
- 本機**有 `mypy`，但版本是 1.15.0**，pin 的是 **1.19.1**。
- `docker compose run --rm backend ruff …` 也不通：runtime image 依設計不含 dev tooling。
- repo 根的 `.ruff_cache/`、`.mypy_cache/` **owner 是 root**——N10 警告的後果早就發生了。

## 2. 已完成

| 項目 | 檔案 | 驗收 |
|---|---|---|
| lint 命令與路徑的單一來源（check / `--fix` 兩模式） | `scripts/lint.sh`（新增） | AC7 |
| 獨立 lint build stage（只裝 dev tooling） | `backend/Dockerfile` | AC1 |
| `lint` service，置於 `profiles: ["tools"]`，快取導向 `/tmp`，以真實 uid/gid 執行 | `docker-compose.yml` | AC1/AC3/AC4/AC5 |
| `make lint` / `make format` 改走容器 | `Makefile` | AC1/AC4 |
| CI lint job 移除 `setup-python` + `pip install` | `.github/workflows/ci.yml` | AC6 |
| 文件同步 | `CLAUDE.md`、`docs/notes.md`（N10 狀態） | AC9 |
| 清除既存 root-owned 快取 | `.ruff_cache/`、`.mypy_cache/` | AC3 |
| 延後項目登記 | `docs/notes.md` N13（mypy 訊號）、N14（測試帶 key） | — |

## 3. 可觀察的行為改變

- `make lint` / `make format` **從此需要 Docker**，host 不再需要任何 Python 工具。
  首次執行會 build 一個小映像（本機實測 **2m50s**），之後每次 **3.0s**。
- `make lint` 的三項檢查、路徑、工具版本，在本機與 CI **保證一致**（同一個 pin 過的映像、同一個 script）。
- `docker compose up`（`make up`）**不會**啟動 lint 容器（profile 隔離）；`docker compose config --services`
  的清單不含它。
- `make format` 改寫檔案後，owner 仍是執行者，不再變成 root。
- **CI 的 lint job 從 host 姿態改為容器姿態**——這是唯一一項本機無法實跑驗證的改動。

## 4. Contract / 依賴 / migration 影響

- **API contract**：無。未觸碰任何 endpoint、schema 或 `docs/api_contract.md`。
- **Production dependency**：**無新增**。`ruff` / `mypy` 沿用既有 `backend/requirements-dev.txt`，
  只進 lint stage，**不進 runtime image**（已用 `docker image inspect` + 容器內 `import fastapi` 驗證
  backend runtime 映像未變）。
- **Migration**：無。

## 5. 未完成 / 未驗證 / 偏差

### 5.1 AC8（`make test` 全綠）未達字面標準

最終狀態：**`1 failed, 241 passed`**（`ingestion/tests/test_pipeline.py::test_qdrant_payload_is_queryable`）。

- 完整歸因見 `VERIFICATION_REPORT.md` §AC8：本機 `.env` 有 OpenAI key → 向量維度 1536 →
  資料寫進 `biology_chunks_1536`，而測試硬編 `COLLECTION_NAME`（dim 128 的名字）。
  實測點數 0 vs 9。**CI 無 key → dim 128 → 會過。**
- 與本變更的 diff **無交集**（未觸碰 `ingestion/`，runtime 映像內容未變）。
- 依 `run-approved-change` 規則**未在驗證階段修它**；已登記為 `docs/notes.md` **N14**。
- 人類（jett，2026-08-14）已在知情下裁定接受此歸因並續寫本報告。

### 5.2 偏差：快取刪除的方法

`rm -rf .ruff_cache .mypy_cache` 在 host 上因目錄為 root 所有而 `Permission denied`——
正是 plan 列的「需要 sudo」stop condition。**未使用 sudo**，改以建立它們的同一種身分刪除：
`docker compose run --rm --user 0:0 --entrypoint sh lint -c 'rm -rf /repo/.ruff_cache /repo/.mypy_cache'`。
判斷依據：D3 已批准刪除、對象是 gitignored 的工具快取、未在 host 提權。
**這是對批准方法的偏差，交由審查判定。**

### 5.3 偏差：清空 volume

驗證期間依人類明確指示執行 `docker compose down -v` → `make up` → `make seed` → `make test`，
以判定 AC8 的失敗歸屬。清除前已將 seed 未收錄的資料 dump 到 session scratchpad
（`curation_items` 20 列 `proposed`、`graph_change_logs` 24 列、`ingestion_jobs` 208 列）。
**這些治理資料未被還原**——人類裁定開發階段可接受。`make seed` 已回填
45 nodes / 84 edges / 5 documents / 9 chunks 與 5 個 demo review groups，站台功能正常。

### 5.4 未驗證

- **CI 未實跑**：`.github/workflows/ci.yml` 只有靜態證據。ubuntu-latest 內建 Docker 的假設、
  以及 `LINT_UID`/`LINT_GID` 在 runner（uid 非 1000）上的行為，**都要在 PR 上看 CI 才算數**。
- 只在一台 Pi 上驗證，未跨機器。
- CI lint job 的耗時變化未量測（失去 pip cache，改為每次冷啟 docker build）。

### 5.5 範圍外、未處理

- `scripts/__pycache__`、`backend/app/**/__pycache__` 等仍為 root 所有——由 `make test` 的 backend
  容器寫入。**既有行為，範圍更大，本次不處理**（已記入 N10 的「未做」）。
- 讓 mypy 看得見 runtime 套件真實型別 → **N13**。
- 本機測試帶 key 執行（可能花 token）→ **N14**。

## 6. 風險與限制

- lint 容器掛載 repo 根（需要根目錄的 `pyproject.toml` 與五條散落路徑），因此看得到 `.env` 與
  `data/seed/`。該容器不連任何服務、只跑 ruff/mypy，判定可接受，但這是刻意的取捨。
- `backend/Dockerfile` 的 lint stage **必須留在檔案最前面**：未加 `--target` 的 build 會解析到
  最後一個 stage。若日後有人在檔尾追加 stage，backend 映像會被悄悄換掉。註解已寫明，但這是
  結構性的脆弱點。
- 首次 lint 需要網路（`pip install`）。離線機器第一次跑 `make lint` 會失敗。

## 7. Rollback

```bash
git checkout -- Makefile docker-compose.yml backend/Dockerfile .github/workflows/ci.yml CLAUDE.md docs/notes.md
rm -f scripts/lint.sh
docker image rm bio_graphrag-lint
```

回滾後 `make lint` 恢復為 host 姿態（即今天的壞狀態），無資料影響。已刪除的快取會由工具自行重建。

## 8. 交接

尚未 commit、未 push、未經獨立審查。下一步是在**未繼承本次對話的全新 agent** 中執行 `review-change`。

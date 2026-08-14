# Implementation Plan: containerize-lint

對應 `docs/notes.md` 的 **N10**（2026-08-13 由 `close-approve-item-backdoor` 第四輪獨立審查者提出，S-C）。

## Objective

讓 lint 與 type-check 具備**容器化入口**，使「lint 全過」成為審查者在乾淨機器上可獨立複核的宣稱，
而不是只能採信實作者自述。

今天的問題不是「lint 沒跑」，而是**沒人能重跑**：`make lint` 依賴 host 上的 `ruff` / `mypy`，
本機沒有 `ruff`（見 Current-State Evidence），有的 `mypy` 還是 1.15.0——不是 pin 的 1.19.1。
於是同一個指令在實作者、審查者、CI 三處跑的是**三種不同的東西**。

## In Scope

- 新增單一 lint 命令來源 `scripts/lint.sh`（check 與 fix 兩個模式）。
- `backend/Dockerfile` 新增一個獨立的 lint build stage（含 dev tooling）。
- `docker-compose.yml` 新增 `lint` service（放在 profile 內，不隨 `make up` 啟動）。
- `Makefile` 的 `lint` / `format` 改走容器。
- `.github/workflows/ci.yml` 的 lint job 移除 host 的 `setup-python` + `pip install`。
- 文件同步：`Makefile` 註解、`CLAUDE.md` Commands 區塊、`docs/notes.md` N10 狀態。
- 清除 repo 內既存的 root-owned `.ruff_cache/` 與 `.mypy_cache/`。

## Out of Scope

- **不修任何 lint / type 錯誤**。本變更只換執行方式，不改 production 程式；若容器內冒出新錯誤，
  屬於 D1 的後果，依 D1 的決定處理（見 Human Decisions）。
- 不新增 lint 規則、不改 `pyproject.toml` 的 `[tool.ruff]` / `[tool.mypy]` 設定。
- 不動 `make test` / `make eval` / CI 的 test job。
- 不處理 `docs/notes.md` 的其他 N 項。
- 不建立 pre-commit hook。

## Current-State Evidence

- **Repository state**：`main` @ `b71481f`，工作區有兩個未提交修改：
  - `docs/agent-guideline.md`（**未解釋的修改**，疑為 skill-forge render 產物，已向人類提問但尚未回覆。
    不屬本變更，實作期間**不得觸碰**。）
  - `docs/notes.md`（本次會期依人類指示新增 N12，已解釋。）
- **Relevant files and symbols**：
  - `Makefile:39-50` — `LINT_PATHS = backend/app ingestion backend/tests ingestion/tests scripts`；
    `lint:` 直接呼叫 `ruff check` / `ruff format --check` / `mypy backend/app ingestion scripts`；
    `format:` 直接呼叫 `ruff check --fix` / `ruff format`。註解自承「needs dev tools: pip install …」。
  - `backend/requirements-dev.txt` — `ruff==0.15.21`、`mypy==1.19.1`，開頭註明
    「Not installed into the runtime image」。
  - `backend/Dockerfile` — 單一 stage，`FROM python:3.12-slim`，只裝 `requirements.txt`，
    **未 COPY `pyproject.toml`**（而 ruff/mypy 設定都在 repo 根的 `pyproject.toml`）。
  - `docker-compose.yml` — `backend` service 掛載 `./backend/app`、`./scripts`、`./ingestion`、
    `./schema`、`./prompts`、`./data`；**未掛 `pyproject.toml`、未掛 `backend/tests`、`ingestion/tests`**。
  - `.github/workflows/ci.yml:16-28` — lint job 用 `setup-python` + `pip install -r backend/requirements-dev.txt`
    + `make lint`（host 姿態）；同檔 test job 全程 Docker。
  - `.gitignore:12-13` — `.mypy_cache/`、`.ruff_cache/` 已被忽略。
- **Existing behavior and baseline**（唯讀觀察，未執行 `make lint`）：
  - `which ruff` → 無；`which mypy` → `/usr/bin/mypy`，`mypy --version` → **1.15.0**（pin 是 1.19.1）。
    因此本機 `make lint` 會在**第一行**就 `ruff: not found` 而失敗。
  - `docker compose run --rm backend ruff …` 同樣不可行：runtime image 依設計不含 dev tooling。
  - repo 根已存在 `.ruff_cache/`、`.mypy_cache/`，**owner 皆為 root**，時間戳 Jul 22——
    N10 警告的那個後果**已經發生過**。
  - CI lint job 目前是綠的（host、mypy 1.19.1、**只裝 dev tooling、未裝 runtime 依賴**）。
    這一點是 D1 的關鍵輸入。
  - 本地已有 `python:3.12-slim` 映像（`docker image ls`），首次 build 不需重拉 base。

## Acceptance Criteria

- **AC1** 在**沒有 host `ruff`** 的機器上，`make lint` 能完整跑完三項檢查並回傳正確結果。
- **AC2** 負向對照：故意製造一個 ruff 違規時 `make lint` 必須**失敗**；故意製造一個 mypy 型別錯誤時
  `make lint` 必須**失敗**。（依 `docs/notes.md` N11：宣稱守門的指令要證明它會紅。）
- **AC3** 執行 `make lint` 與 `make format` 後，repo 內**不新增任何 root 所有的檔案或目錄**；
  既存的 root-owned `.ruff_cache/`、`.mypy_cache/` 已被清除。
- **AC4** `make format` 改寫的檔案，owner 與執行者相同（不變成 root）。
- **AC5** `docker compose up -d`（即 `make up`）**不會**啟動 lint service；`docker compose config --quiet` 通過。
- **AC6** CI lint job 不再安裝 host Python 套件，仍對相同路徑執行相同三項檢查。
- **AC7** lint 的命令與路徑清單**只有一處定義**（`scripts/lint.sh`），Makefile、compose、CI 都引用它。
- **AC8** `make test` 仍通過（確認 backend runtime image 未被 Dockerfile 改動破壞）。
- **AC9** 文件同步：`CLAUDE.md` Commands、`Makefile` 註解、`docs/notes.md` N10 狀態一致。

## Contract, Schema, Dependency, and Migration Impact

- **API contract**：無。不動 `docs/api_contract.md`、不動任何 endpoint。
- **Schema / migration**：無。
- **Production dependency**：**無新增**。`ruff` / `mypy` 版本沿用既有 `backend/requirements-dev.txt`，
  且只進 lint stage，不進 runtime image。
- **開發者介面變更**：`make lint` / `make format` 從此需要 Docker（本專案本來就以 Docker 為唯一執行環境）。
  首次執行會 build 一個小映像。

## Execution Policy

- **Plan revision**：1
- **Risk level**：**low**（只動建置／工具設定，不觸 production 程式與資料）
- **Automation mode**：**建議 `supervised-auto`**（待人類明確批准；未批准前預設 `one-task-at-a-time`）
- **Auto-approved task IDs（`supervised-auto` only）**：T1–T6
- **Approved file/path scope**：
  - `scripts/lint.sh`（新增）
  - `backend/Dockerfile`
  - `docker-compose.yml`
  - `Makefile`
  - `.github/workflows/ci.yml`
  - `CLAUDE.md`、`docs/notes.md`
  - `changes/containerize-lint/*`
  - 刪除：`.ruff_cache/`、`.mypy_cache/`（gitignored 快取）
- **Human checkpoints**：
  - D1 決定（lint 映像基底）必須先有答案才能開始 T2。
  - 若容器內 lint 出現既有程式碼的錯誤 → 停止，回報清單，不自行修 production 程式。
- **Mandatory stop conditions**：
  - 需要 `sudo` 才能刪除 root-owned 快取。
  - 需要改動 `pyproject.toml` 的 lint 設定才能讓檢查通過。
  - 觸碰 `docs/agent-guideline.md`（不屬本變更的未解釋修改）。
  - 需要新增 production dependency，或需要改動任何 `backend/app` / `ingestion` 下的程式。
- **Commit/push permission**：**No unless separately approved after review.**

## Tasks

### Task 1 — `scripts/lint.sh`：lint 命令的單一來源

- **Files/symbols**：新增 `scripts/lint.sh`（可執行）。
- **Implementation**：把 `Makefile:41-50` 的路徑清單與三個命令搬進 shell script，
  `set -euo pipefail`；無參數＝check 模式（`ruff check` / `ruff format --check` / `mypy`），
  `--fix` ＝ format 模式（`ruff check --fix` / `ruff format`）。路徑清單只在此處定義。
- **Tests and container command**：`bash -n scripts/lint.sh`（語法檢查）；此時尚無容器可跑，
  完整驗證留待 T4。
- **Stop/handoff**：不改 Makefile，交付 T2。

### Task 2 — `backend/Dockerfile`：新增 lint stage

- **Files/symbols**：`backend/Dockerfile`。
- **Implementation**：依 D1 的決定新增一個具名 stage（例如 `FROM python:3.12-slim AS lint`），
  只安裝 `requirements-dev.txt`，`WORKDIR /repo`。現有 runtime stage 的**內容不改**
  （必要時只加 `AS runtime` 標籤）。
- **Tests and container command**：
  `docker compose build backend`（確認 runtime image 仍能 build，預設 stage 未變）。
- **Stop/handoff**：若 `docker compose build backend` 因新 stage 而改變預設建置目標 → 停止。

### Task 3 — `docker-compose.yml`：`lint` service

- **Files/symbols**：`docker-compose.yml`。
- **Implementation**：新增 `lint` service：`build: {context: ./backend, target: lint}`、
  `profiles: ["tools"]`（使其不隨 `up` 啟動）、`working_dir: /repo`、
  `volumes: [.:/repo]`（需要 `pyproject.toml` 與全部 lint 路徑，故掛 repo 根）、
  `environment: RUFF_CACHE_DIR=/tmp/ruff, MYPY_CACHE_DIR=/tmp/mypy`（快取離開 repo）、
  `user: "${LINT_UID:-1000}:${LINT_GID:-1000}"`（由 Makefile 帶入真實 uid/gid）、
  `entrypoint: ["bash", "scripts/lint.sh"]`。無 `depends_on`。
- **Tests and container command**：
  `docker compose config --quiet`；`docker compose up -d` 後 `docker compose ps` 不含 lint（AC5）。
- **Stop/handoff**：交付 T4。

### Task 4 — `Makefile`：lint / format 改走容器

- **Files/symbols**：`Makefile`（`lint`、`format` target 與其上方註解；`LINT_PATHS` 移除，改由 script 持有）。
- **Implementation**：
  ```make
  LINT_UID := $(shell id -u)
  LINT_GID := $(shell id -g)
  export LINT_UID
  export LINT_GID

  lint:
  	docker compose run --rm lint

  format:
  	docker compose run --rm lint --fix
  ```
  註解改寫為「在容器內執行，host 不需安裝任何工具」。
- **Tests and container command**：
  - `make lint`（AC1；host 無 ruff 仍須跑完）
  - 負向對照（AC2）：暫時在 `scripts/` 下加入一個 unused import → `make lint` 必須失敗；
    還原後改成一個明確型別錯誤 → `make lint` 必須失敗；兩者都還原並確認回綠。
  - `make format` 後 `git status` 應乾淨或只含預期改動，且 `ls -l` 顯示 owner 未變成 root（AC4）。
- **Stop/handoff**：若既有程式碼在容器內出現錯誤 → **停止並回報**，不修 production 程式。

### Task 5 — CI lint job 去 host 化

- **Files/symbols**：`.github/workflows/ci.yml` 的 `lint` job。
- **Implementation**：移除 `setup-python` 與 `pip install` 兩個 step，保留 `checkout` 與 `make lint`；
  補一個 `docker compose config --quiet` 或直接讓 `make lint` 觸發 build。
  （ubuntu-latest runner 內建 Docker 與 compose v2。）
- **Tests and container command**：本機無法跑 GitHub Actions；驗證方式為
  `docker compose run --rm lint` 在乾淨環境可獨立完成（等價證據），CI 實跑結果於 PR 上觀察。
  **驗證報告須誠實標示此項為「未在本機執行」。**
- **Stop/handoff**：交付 T6。

### Task 6 — 文件同步與快取清理

- **Files/symbols**：`CLAUDE.md`（Commands 區塊補 lint 指令）、`Makefile` 註解（T4 已含）、
  `docs/notes.md`（N10 補「狀態:」段，比照 N7/N8 的寫法）；刪除 `.ruff_cache/`、`.mypy_cache/`。
- **Implementation**：文件只描述**實際落地**的形態；N10 狀態要寫清楚採用了哪個做法、
  以及「CI 是否已改」。
- **Tests and container command**：`git status --short` 確認未觸碰 `docs/agent-guideline.md`。
- **Stop/handoff**：交付 verify-change。

## Verification Strategy

全部在容器內執行，host 不安裝任何套件。

| 面向 | 命令 | 對應 AC |
|---|---|---|
| 正常 | `make lint` | AC1 |
| **負向對照** | 人為插入 ruff 違規 → `make lint` 必須非 0；人為插入型別錯誤 → 必須非 0；各自還原 | AC2 |
| 邊界（權限） | `find . -user root -not -path './.git/*'` 執行前後比對；`ls -ld .ruff_cache .mypy_cache` | AC3 |
| 邊界（寫入） | `make format` 後 `ls -l` 檢查被改寫檔案的 owner | AC4 |
| 相容 | `docker compose config --quiet`；`make up` 後 `docker compose ps` | AC5 |
| 相容 | `make test` | AC8 |
| 單一來源 | `grep -rn "ruff\|mypy" Makefile docker-compose.yml .github/workflows/ci.yml` 應只見到呼叫，不見路徑清單 | AC7 |

已知基線雜訊：`make test` 的 `test_pipeline_run_is_idempotent` 在非全新 Postgres volume 上會失敗
（既有問題，非本變更造成）。驗證報告須據實標示，不得靜默略過。

## Risks and Unknowns

- **R1 — mypy 看到的東西可能改變（由 D1 決定）。** 若 lint 映像疊在 backend runtime image 上，
  mypy 會第一次看到 fastapi / pydantic / asyncpg 的真實型別，可能一次冒出大量既有錯誤，
  本變更就會從「換執行方式」變成「修型別」。選項 A（只裝 dev tooling）與今天 CI 的環境完全相同，
  **CI 現在是綠的**，故預期不產生新錯誤。
- **R2 — CI 的 uid/gid。** GitHub runner 的 uid 非 1000；`LINT_UID := $(shell id -u)` 會動態帶入，
  應可運作，但未實測。退路：CI step 直接 `docker compose run --rm --user $(id -u):$(id -g) lint`。
- **R3 — 首次 build 成本。** Pi 上 `pip install ruff mypy` 需網路，約數十秒；之後有 layer cache。
  每次 `make lint` 另有約 1–3 秒的容器啟動開銷。以「可複核」換「稍慢」。
- **R4 — 掛載 repo 根。** lint 需要 `pyproject.toml` 與五條路徑，逐一掛載易漏；掛 repo 根較穩，
  代價是容器看得到 `.env`、`data/seed/`。lint service 不連任何服務、不執行專案程式，判定可接受。
- **U1 — 未知：容器內 ruff 0.15.21 對現有程式碼是否全綠。** 本機從未跑過 ruff（沒裝）；
  CI 綠代表**在 CI 的環境**是綠的，且選項 A 與該環境相同 → 預期綠，但**未實測**。

## Rollback

純設定檔變更，無資料影響：

```bash
git checkout -- Makefile docker-compose.yml backend/Dockerfile .github/workflows/ci.yml CLAUDE.md docs/notes.md
rm -f scripts/lint.sh
docker image rm bio_graphrag-lint  # 若已 build
```

已合併後則 `git revert`。回滾後 `make lint` 恢復為 host 姿態（即今天的壞狀態），無其他副作用。

## Human Decisions and Approval

- **Decisions required**：

  **D1 — lint 映像的基底（影響 mypy 看得到什麼）**

  | 選項 | 做法 | 後果 |
  |---|---|---|
  | **A（建議）** | `FROM python:3.12-slim AS lint` + **只裝** `requirements-dev.txt` | 與今天 CI 的環境**完全相同**，CI 綠即預期綠；映像小、build 快。缺點：mypy 對 fastapi/pydantic 等仍是 `ignore_missing_imports`，型別訊號偏弱——但這是**現狀**，不是本變更造成的退步 |
  | B | lint stage 疊在 backend runtime stage 上，再裝 dev tooling | mypy 看得到真實型別，訊號強得多。缺點：極可能一次冒出大量既有錯誤，使本變更失焦；且與 CI 現行結果不再等價 |

  建議 **A**，並把「強化 mypy 訊號」記成 `docs/notes.md` 的獨立後續項（不在本次做）。

  **D2 — Execution Policy**：`supervised-auto`（T1–T6，路徑如上）或 `one-task-at-a-time`。
  本變更 risk = low、不動 production 程式，建議 `supervised-auto`；但 T4 的負向對照會**故意製造失敗**，
  屆時我會在報告中明確區分「人為製造的紅」與「真實的紅」。

  **D3 — 附帶清理**：是否同意刪除 repo 內既存的 root-owned `.ruff_cache/` 與 `.mypy_cache/`
  （皆為 gitignored 快取，刪除無資料風險）。

- **Decisions recorded**（2026-08-14，jett）：
  - **D1 = A**：lint stage 為獨立的 `FROM python:3.12-slim AS lint`，只裝 `requirements-dev.txt`。
    「強化 mypy 訊號（讓它看得到 runtime 套件型別）」記為後續獨立項，不在本次。
  - **D2 = `supervised-auto`**，auto-approved tasks = T1–T6，路徑範圍如 Execution Policy 所列。
  - **D3 = 刪除**既存的 root-owned `.ruff_cache/` 與 `.mypy_cache/`；若需 `sudo` 則停止回報。

- **Status**：**Approved**
- **Approved plan revision**：**2**（rev 1 已交付並經獨立審查；rev 2 為審查處置，見下）
- **Approved risk level and automation mode**：low / `supervised-auto`
- **Approved by/date**：jett / 2026-08-14（rev 1 與 rev 2 同日）

---

## Revision 2 — 審查處置（Approved / jett / 2026-08-14）

依 `REVIEW_REPORT.md`（獨立 reviewer，無 Blocking / 無 High）。**新增路徑**：
`backend/requirements-dev.txt`（僅一行註解，L2）。其餘皆在 rev 1 已批准的路徑內。

| Finding | 裁定 | 任務 |
|---|---|---|
| **M1** `make lint` 永不重建 image → 升 tooling 後本機與 CI 靜默漂移 | **修行為**（不是修宣稱）。實測 `--build` 只多約 2–3 秒；**不引用單一數字**（審查 N-2），基準見 `VERIFICATION_REPORT.md` §風險 | R1 |
| **M2** 兩份報告的 diff base `b71481f` 已失效（main 已推進至 `776438b`，分支已 rebase） | 改為 `776438b`，移除手動 exclude 指示 | R2 |
| **M3** 快取以容器內 root 刪除，繞過「需 sudo 即停止」的 stop condition | **人類裁定：接受本次，且不另立規則**（jett）。報告如實記載裁定與其範圍 | R3 |
| **L1** CHANGE_REPORT §8 與表頭矛盾（「尚未 commit」vs 已 commit） | 更正 | R2 |
| **L2** `requirements-dev.txt:2` 仍寫 host `pip install`，牴觸 `CLAUDE.md` 與工作準則 | **擴充範圍修掉**（一行註解） | R4 |
| **L3** 無關的 N12 commit 搭便車在本分支 | **不 cherry-pick**（重寫分支不划算），在 CHANGE_REPORT 明白揭露 | R2 |
| **L4** stage 順序陷阱只靠註解守 | `backend` service 補 `target: runtime`，讓建置目標與 stage 順序脫鉤 | R5 |
| **L5** 治理資料 dump 只存在 `/tmp` | **搬到 repo 外的持久位置**（jett 裁定），報告記載新位置 | R6 |
| **S1** check 模式改唯讀掛載 | **不做**：要拆 service 或加 override，複雜度不划算 | — |
| **S2** `lint.sh` 誤在 host 執行的防護 | **不做**：`make lint` 是唯一入口，此為邊角 | — |
| **S3** `LINT_UID` fallback 靜默 | **不做**：註解已寫明，同上 | — |

**Verification（rev 2）**：`make lint`（含證明 R1 真的會重建——R4 正好改動 `requirements-dev.txt`）、
`docker compose build backend` + `docker image inspect`（證明 R5 未改變 runtime 映像）、
`docker compose config --quiet`。**不重跑 `make test`**：rev 2 未觸碰任何 runtime 程式，
且 rev 1 已記錄其結果與歸因。

**Mandatory stop conditions（rev 2 沿用 rev 1，另加）**：若 R5 使 `docker compose build backend`
產出不同於 runtime stage 的映像 → 停止。
- **Approval evidence**（審查 N-4：此欄原本留著「尚未批准」的模板句，與上方的
  `Status: Approved` 並存，讀者無從分辨「已批准」與「模板沒填」。現以實際證據取代）：
  - **rev 1**：2026-08-14，jett 在 `plan-change` 交出計畫後，於本 session 的互動式提問中
    逐項選定 D1 = A（lint stage 只裝 dev tooling）、D2 = `supervised-auto`（T1–T6）、
    D3 = 刪除既存 root-owned 快取。三項選擇即構成對 rev 1 範圍、風險等級與自動化模式的批准。
  - **rev 2**：2026-08-14，jett 在獨立審查（`REVIEW_REPORT.md` Round 1）後，於同一 session
    裁定 M3「接受本次且不另立規則」、L2「擴充範圍順手修」、L5「搬到 repo 外的持久位置」，
    並未反對隨附的 M1 / M2 / L1 / L3 / L4 處置表。該表即為 rev 2 的批准範圍。
  - **仍然成立的限制**：批准涵蓋實作與 commit，**不含 push、merge、release**；
    重大計畫變更會使批准失效。

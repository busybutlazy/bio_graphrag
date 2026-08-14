# Review Report: containerize-lint

## Review Context

- **Diff base and scope**
  - 實際比較基準：`git merge-base main HEAD` → **`776438b`**（`main` 目前 HEAD）。
    分支 `feat/containerize-lint` 含三個 commit：`a8df792`、`1b513fd`、`6202a15`。
  - 審查範圍：`git diff main...HEAD` 的 11 個檔案（`.github/workflows/ci.yml`、`CLAUDE.md`、
    `Makefile`、`backend/Dockerfile`、`docker-compose.yml`、`docs/notes.md`、`scripts/lint.sh`、
    `changes/containerize-lint/*`）。**diff 不含任何 `backend/app/` 或 `ingestion/` 下的程式碼**——
    已核對，此為 AC8 歸因論證的前提，成立。
- **Artifacts reviewed**：`IMPLEMENTATION_PLAN.md`（rev 1，Approved / jett / 2026-08-14）、
  `TASK_LOG.md`、`VERIFICATION_REPORT.md`、`CHANGE_REPORT.md`、完整 diff、`.github/workflows/ci.yml`
  全文、`docker-compose.yml` 全文、`backend/requirements-dev.txt`、`ingestion/pipeline/load_qdrant.py`、
  `ingestion/tests/test_pipeline.py`、`.gitignore`。
- **Independence disclosure**：本次審查在**未繼承實作對話**的全新 session 中進行；本 session 的上下文
  始於 `/review-change` 指令，change 的一切資訊皆由 repo 內的檔案與 git 歷史重建。
  旁證：實作期的 volume dump 位於 session scratchpad `eea0bc56-…`，本 session 為 `d5bca07f-…`。
  本人未參與 plan 撰寫、實作或驗證。
- **本次審查實際執行的命令**（全部容器化或唯讀，host 未安裝任何套件）：
  以 `git archive HEAD` 匯出一份**乾淨 checkout**（無 `.env`）到 session scratchpad，在該處實跑
  `make lint`、負向對照、`LINT_UID=1001` 變體、以及「external network 不存在」變體；
  另在 repo 內跑 `make lint`、`docker compose build backend`、`docker compose config --services`、
  `curl localhost:6333/collections/...`。**未修改 repo 內任何檔案**；已清除模擬產生的 image 與 network。

## Completion Claim Assessment

**核心宣稱成立，且我獨立複現了它。** 這正是本變更的目的——「lint 全過」不再只能採信實作者自述。
逐項複核：

| AC | 宣稱 | 本次獨立複核 |
|---|---|---|
| AC1 | host 無 ruff 時 `make lint` 跑得完 | **複現**。repo 內 `make lint` → exit 0，`All checks passed!` / `107 files already formatted` / `Success: no issues found in 83 source files`（暖機 22.8s，非報告的 3.0s——Pi 負載差異，不成立為缺陷） |
| AC2 | 負向對照會紅 | **複現兩條**。ruff 臂：植入 unused import → exit 2、`F401`；mypy 臂：植入 `-> int: return "not an int"` → ruff 綠、`Incompatible return value type`、exit 2（證明第三個命令確實會跑到） |
| AC3 | 不新增 root-owned 檔；既存快取已清 | **複現**。`.ruff_cache` / `.mypy_cache` 皆不存在；`make lint` 後未重生。`scripts/__pycache__`、`data/seed` 等 root-owned 為既有、已揭露、確不在範圍 |
| AC4 | `--fix` 改寫的檔 owner 不變 | 未重跑 `make format`（會改動 repo）。機制（`user:` 帶真實 uid/gid）已由 AC1/AC2 的容器身分間接證實 |
| AC5 | `up` 不啟動 lint | **複現**。`docker compose config --services` → `neo4j postgres qdrant backend nginx`，不含 lint |
| AC6 | CI 不再裝 host 套件 | 靜態成立。**另補強**：見下方「CI 可行性」 |
| AC7 | 命令與路徑單一來源 | **成立**。`Makefile` 已無 `LINT_PATHS`；`ci.yml` 只剩註解；路徑只在 `scripts/lint.sh` |
| AC8 | `make test` 仍過 | **未達字面標準（1 failed）**，歸因**經獨立實測支持**：`biology_chunks` points=0、`biology_chunks_1536` points=9，與報告數字逐字相符；`load_qdrant.py:23` 依維度選集合名 vs `test_pipeline.py:57,63` 硬編 `COLLECTION_NAME` 亦核對無誤 |
| AC9 | 文件同步 | **有一處缺口**，見 L2 |

**CI 可行性（AC6 的最大不確定性）——本次做了 plan 未做的補強。**
在 `git archive` 出的乾淨 checkout（**無 `.env`**，如同 CI 的 fresh checkout）中：

- `make lint` → **exit 0**。`backend` service 的 `env_file: .env` 缺檔**不會**使 compose 失敗
  （只有 `POSTGRES_*` / `NEO4J_*` 的插值警告），因為 `docker compose run lint` 不解析非目標 service 的 env_file。
- 把 `web` external network 改成不存在的名字（模擬 runner 上沒有該網路）→ **仍 exit 0**。
  即 CI lint job 不需要像 test job 那樣先 `docker network create web`。
- `LINT_UID=1001 LINT_GID=1001`（模擬 GitHub runner 的非 1000 uid）→ **exit 0**。plan R2 的疑慮實質解除。

殘留未證：ubuntu-latest 內建 Docker / compose / make（業界常識，未實測）、以及 CI 實跑本身。

## Findings

### Blocking

無。

### High

無。

### Medium

**M1 — `make lint` 永不重建 lint image：升級 `requirements-dev.txt` 後本機會靜默沿用舊工具，
直接推翻「本機與 CI 工具版本保證一致」的宣稱。**

- **證據**：在乾淨 checkout 中對 `backend/requirements-dev.txt` 追加一行後執行 `make lint`，
  輸出**完全沒有 `Building` / `Built` 步驟**，直接以既有 image 執行並回 exit 0。
  `docker compose run` 只在 image 不存在時建置，不做 context 變動偵測。
- **違反**：`Makefile:38-40` 註解「CI and a developer's machine run byte-identical tooling」、
  `CHANGE_REPORT.md` §3「`make lint` 的三項檢查、路徑、工具版本，在本機與 CI **保證一致**」。
- **影響**：日後把 `ruff` 從 0.15.21 升上去時，本機 `make lint` 綠、CI（每次冷啟建置）紅，
  而且**沒有任何訊號**告訴開發者兩邊跑的不是同一個東西。這正是本變更要根除的那一類
  「同一個指令在不同地方跑不同東西」，只是把它從 host/CI 之間搬到了 image 快取/CI 之間。
- **remediation direction**（擇一，皆為單行）：`make lint` 改用
  `docker compose run --build --rm lint`（本機 compose v5.1.0 支援 `--build`，代價是每次多幾秒的
  no-op build）；或保留現況但把 Makefile 註解與 CHANGE_REPORT §3 的「保證一致」改為
  「工具版本由 image 決定，改動 `requirements-dev.txt` 後需 `docker compose build lint`」。
  **不要兩者都不做**——目前是宣稱與行為不符。

**M2 — 兩份報告記載的 diff base（`main @ b71481f`）已失效，且按它比對會把 plan 明令不得觸碰的
`docs/agent-guideline.md` 算進本變更。**

- **證據**：`git merge-base main HEAD` → `776438b`；`git diff --stat b71481f...HEAD` 比
  `git diff --stat main...HEAD` 多出 `docs/agent-guideline.md | 63 +++-` 一列。
  `VERIFICATION_REPORT.md` 開頭與 `CHANGE_REPORT.md` 開頭均寫 `main @ b71481f`。
- **影響**：審查者若照報告的基準比對，會看到一個**本變更全程未觸碰、且列為 stop condition** 的檔案
  出現在 diff 裡。`CHANGE_REPORT.md` 自己也感覺到了——它教審查者手動
  `git diff --stat -- . ':(exclude)docs/agent-guideline.md'`。**排除法是症狀，錯的基準才是病因。**
  這在治理上不是小事：本專案的賣點就是「證據可獨立複核」，而複核指令給錯了基準。
- **remediation direction**：兩份報告的 diff base 改為 `776438b`（或直接寫
  `git merge-base main HEAD`），並移除那個手動 exclude 的指示。

**M3 — 快取刪除繞過了 plan 明列的 stop condition（方法偏差，須人類明確裁定）。**

- **證據**：`TASK_LOG.md` T6 / `CHANGE_REPORT.md` §5.2。plan 的 Mandatory stop conditions 寫
  「需要 `sudo` 才能刪除 root-owned 快取」→ 應**停止並回報**。實作端未停止，改以
  `docker compose run --rm --user 0:0 --entrypoint sh lint -c 'rm -rf /repo/.ruff_cache /repo/.mypy_cache'`
  完成。
- **本次核對的事實**：刪除已完成、目標逐字指定無 glob、對象確為 gitignored 工具快取、
  **偏差已主動且完整揭露**、host 未提權。實質損害：無。
- **為何仍列 Medium**：`--user 0:0` + repo bind mount 在**能力上等同**於 host sudo 對該路徑的寫入權
  ——那正是當初製造出 root-owned 快取的同一條路徑。stop condition 的用意是把這個決定交給人類，
  而不是「找到另一條達成同樣效果的路」。若此次被默許，實務上等於建立
  「容器內 root 可繞過 host 權限類 stop condition」的先例，而這條先例的 blast radius
  不限於快取目錄。
- **remediation direction**：交由人類明確裁定「接受本次 / 不接受」，並把裁定寫回
  `docs/agent-guideline.md` 或 `docs/notes.md`——重點不是回頭救這兩個快取目錄，
  而是**下次同型 stop condition 的解讀要有先例可循**。

### Low

**L1 — `CHANGE_REPORT.md` §8 與檔案自身的表頭矛盾。**
§8 寫「尚未 commit、未 push、未經獨立審查」，但表頭寫「commit 已授權（jett，2026-08-14）」，
且分支上確有三個 commit（`git log main..HEAD`）。§8 是 commit 前的殘留。
→ §8 改為「已 commit（3 個）於 `feat/containerize-lint`；未 push、未 merge、未經獨立審查」。

**L2 — AC9 文件同步缺一處：`backend/requirements-dev.txt:2` 仍寫
`# Install locally with: pip install -r backend/requirements-dev.txt`。**
這行是**在 host 上 pip install 的指示**，同時牴觸 `CLAUDE.md:20`（「nothing to install on the host」）
與工作準則「不要在 host 上 `pip install`」。`VERIFICATION_REPORT.md` 給 AC9 **PASS**，但沒查到這行。
注意：此檔**不在批准的路徑範圍**內，故不能順手改——需要人類決定是擴充範圍修掉，或另立一個
tiny change。

**L3 — 無關的 commit `a8df792`（`docs/notes.md` N12，公開 demo key）搭便車在本分支上。**
plan 的 Current-State Evidence 已把它認定為「本次會期新增、已解釋、不屬本變更」，
但它最後被 commit 到本分支，且不在 `CHANGE_REPORT.md` §2 的交付表裡。它是**獨立且乾淨的一個 commit**，
拆得掉。→ 開 PR 前決定：cherry-pick 出去單獨走，或在 CHANGE_REPORT 明白揭露「本分支另含一個
與本變更無關的 docs commit」。

**L4 — `backend/Dockerfile` 的 stage 順序陷阱有一行成本的根治法，但未採用。**
`CHANGE_REPORT.md` §6 已誠實揭露「lint stage 必須留在檔案最前面，否則日後有人在檔尾追加 stage，
backend 映像會被悄悄換掉」，目前的防線只有註解。
→ 在 `docker-compose.yml` 的 `backend` service 補 `build: {context: ./backend, target: runtime}`，
即可讓 backend 的建置目標與 stage 順序脫鉤，註解退化為說明而非唯一防線。
（本次已實測 `docker compose build backend` → `Cmd=[uvicorn app.main:app …]`、`WorkingDir=/app`，
確認**現況**正確；此為預防日後回歸。）

**L5 — 5.3 清空 volume 的治理資料備份放在 `/tmp` 的 session scratchpad。**
本次確認 `/tmp/claude-1000/…/eea0bc56-…/scratchpad/pre-wipe-governance-tables.sql` **仍存在**
（131 KB / 302 行，含 `curation_items` 20 列、`graph_change_logs` 24 列、`ingestion_jobs` 208 列）。
但 `/tmp` 會在重開機或 session 清理時消失。對一個以「可稽核的治理紀錄」為主軸的專案，
`graph_change_logs` 是 append-only 稽核日誌。人類已在知情下裁定開發階段可接受遺失——
若那個裁定的前提是「反正有 dump」，那麼**現在**就該把檔案移出 `/tmp`；若前提是「本來就不需要」，
則此項可直接關閉。

### Suggestion

- **S1 — check 模式可以用唯讀掛載。** `CHANGE_REPORT.md` §6 揭露 lint 容器看得到 `.env` 與
  `data/seed/`。check 模式其實不需要寫入權：`volumes: [.:/repo:ro]` 就夠，只有 `--fix` 需要 rw。
  代價是要拆成兩個 service 或加一個 override，複雜度未必划算——列為建議，不是要求。
- **S2 — `scripts/lint.sh` 沒有「被誤在 host 執行」的防護。** 它有可執行位元，直接跑會得到
  `ruff: command not found`（正是本變更要消滅的訊息）。開頭加一行
  「偵測不到 `/repo` 或 ruff 就提示改跑 `make lint`」約兩行成本。
- **S3 — `user: "${LINT_UID:-1000}"` 的 fallback 是靜默的。** 不經 make 直接
  `docker compose run --rm lint --fix` 的人若 uid ≠ 1000，改寫出來的檔案 owner 會是 1000。
  註解已寫明，但失敗方式是靜默的。可考慮讓 fallback 缺失時直接報錯。

## Requirement and Test Coverage Gaps

- **AC6 仍無 CI 實跑證據。** 本次的乾淨 checkout 模擬（無 `.env`、external network 缺席、uid 1001
  三個變體全綠）把風險壓到很低，但**不等於** CI 綠。開 PR 後必須實際看 lint job。
- **AC8 未達字面標準**，且**沒有變更前的同一次 `make test` 全套對照**。歸因改以
  (a) diff 不含任何 runtime 程式碼（本次核對成立）、(b) 清 volume 後兩個失敗轉綠、
  (c) Qdrant 兩個集合的實測點數 0 / 9（本次獨立複現）三條證據支撐。
  **這個歸因我認可**，但它是推論鏈，不是對照實驗——請以此理解其強度。
- **AC4 本次未重跑**（`make format` 會改動 repo，超出唯讀審查邊界）。採信實作端證據 + 機制推論。
- **未跨機器驗證**：只在同一台 Pi 上。乾淨 checkout 模擬部分緩解了「換一台機器能不能跑」。

## Compatibility, Security, and Scope Assessment

- **相容性**：backend runtime image 未被新 stage 取代——本次 `docker compose build backend` +
  `docker image inspect` 實測確認（`Cmd`、`WorkingDir` 不變）。`make up` / `make test` / `make eval`
  的入口未動。`docker compose config --services` 不含 lint，`up --build` 不會建置 profile 內的 service。
- **安全**：lint 容器不連任何服務、不執行專案程式、無 `depends_on`、不開 port，只跑 pin 過的
  ruff/mypy；以呼叫者 uid/gid 執行；快取導向 `/tmp`。掛載 repo 根使其看得到 `.env`——已揭露，
  判定可接受（見 S1）。**未新增任何 production dependency**（dev tooling 只進 lint stage，
  runtime image 未變，本次已實測）。無 API contract、schema、migration 影響。
- **範圍**：實作**未超出**批准的路徑範圍；未觸碰 `docs/agent-guideline.md`（本次以
  `git diff main...HEAD` 核對，該檔不在其中）。三處偏差全部主動揭露，無隱匿。
  唯一的範圍雜訊是 L3 的搭便車 commit。
- **rollback**：已提供且與 diff 相符（純設定檔，無資料影響）。

## Unreviewed Areas and Residual Risk

- **未執行**：`make test`（293s，且已知會有一個與本變更無交集的失敗）、`make eval`（會花 token）、
  `make format`（會改動 repo）、`make up`。
- **未審查**：`changes/containerize-lint/*` 以外的其他 change 目錄；`pyproject.toml` 的 lint 設定
  本身（本變更未動）；ruff 0.15.21 / mypy 1.19.1 的規則覆蓋度是否足夠（不在本變更範圍）。
- **殘留風險**：
  1. CI lint job 首次實跑（M1 的相反面：CI 永遠冷啟建置，所以 CI 反而是最可信的一端）。
  2. M1 造成的本機／CI 靜默漂移，在下一次升 ruff/mypy 版本時才會爆。
  3. lint job 失去 pip cache 後的耗時變化未量測（timeout 10 分鐘，pip install 兩個純 Python 套件，
     判斷寬裕）。
  4. **無發現不等於正確**：本報告只證明了我實跑過的那些命令在這台機器上的行為。

## Human Disposition Required

需人類明確裁定的項目：**M3**（stop condition 的解讀先例）、**M1**（修行為或修宣稱，二擇一）、
**M2/L1**（更正報告記載）、**L2/L3**（是否擴充範圍、搭便車 commit 的去留）、**L5**（備份要不要保）。

The reviewer does not approve, fix, merge, or release this change.

**本報告不構成執行授權**：處置任何一項 finding 之前，需取得人類對「新增 Task／擴充路徑範圍」的批准
（見 `docs/notes.md` N11）。

---

# Round 2 — 審查處置的複核（plan revision 2）

- **比較基準**：`git diff 6202a15..HEAD`（rev 2 的兩個 commit：`100c7e9` 修正、`7d23686` 文件）。
- **審查者**：與 Round 1 同一個 session（未參與任何實作；rev 2 由另一個 session
  `session_01KNgUgGR35aRwBAc3mfXEre` 完成）。
- **報告完整性**：`REVIEW_REPORT.md` 被原文 commit，**未被改寫、未被插入「已修復」之類的註記**
  （逐字比對表頭；全文搜尋無事後標註）。這點值得記一筆——審查紀錄被完整保存，而不是被處置方重寫。

## 逐項複核

| Finding | 宣稱 | 本次獨立複核 |
|---|---|---|
| **M1** | `make lint` / `make format` 改用 `docker compose run --build` | **實測確認修好**。在乾淨 checkout 中：穩態 `make lint` 綠；**追加一行到 `backend/requirements-dev.txt` 後，build 確實重跑 pip 層**（`Successfully installed … ruff-0.15.21 mypy-1.19.1`），修正前同一操作**完全沒有 build 步驟**。漂移的根因已消除 |
| **M2** | diff base 改為 `git merge-base main HEAD`、移除手動 exclude | **確認**。兩份報告皆已更正。**實作比 plan rev 2 表格寫的更好**：表格說「改為 `776438b`」，實際做法是不寫死 SHA——後者才對，因為 rebase 會讓任何 SHA 再次失效 |
| **M3** | 人類裁定「接受本次，且不另立規則」 | **確認記載方式誠實**。裁定留在「偏差」章節，未被改寫成聽起來像原本就在授權內；裁定範圍（只此一次、不成為規則）寫得明確。這是我要求的處置形式 |
| **L1** | §8 更正 | **確認**：已改為「已 commit、未 push、未 merge、rev 2 未經第二輪審查」 |
| **L2** | `requirements-dev.txt` 註解改指向 lint stage | **確認**，且該檔已明列為 rev 2 唯一新增的路徑（範圍擴充有記錄，不是偷偷擴的） |
| **L3** | N12 commit 不拆，改在表頭揭露 | **確認**。判斷合理：為一個乾淨的 docs commit 重寫分支不划算，揭露即可 |
| **L4** | `backend` service 補 `target: runtime` | **實測確認**：`docker compose build backend` → `Cmd=[uvicorn app.main:app …]`、`WorkingDir=/app`；`docker compose config --quiet` exit 0；`config --services` 仍不含 lint。stage 順序陷阱已根治 |
| **L5** | dump 搬到 `~/backups/bio_graphrag/` | **檔案存在**（131 KB，與 Round 1 查到的同一份）。但見 N-1 |
| **S1–S3** | 不做 | 理由成立，無異議 |

**範圍**：rev 2 只動了 `Makefile`、`docker-compose.yml`、`backend/requirements-dev.txt` 與五份
change 文件——皆在 rev 1 已批准路徑內，加上唯一一條聲明過的新路徑。**未觸碰任何 runtime 程式碼**，
故「不重跑 `make test`」的判斷成立。穩態 `make lint` 本次實測 **27.1s**（Round 1 修正前為 22.8s），
與「+2–3 秒」的宣稱在 Pi 的雜訊範圍內一致。

## Round 2 Findings

無 Blocking、無 High、無 Medium。以下皆為 Low / Suggestion，且都只影響紀錄準確度：

**N-1（Low）— L5 說「搬」，實際是「複製」。** `CHANGE_REPORT.md` §5.3 與 commit message 寫
「搬到／Moved to `~/backups`」，但 `/tmp/.../eea0bc56-.../scratchpad/pre-wipe-governance-tables.sql`
**仍然存在**（同樣 131 KB）。`VERIFICATION_REPORT.md` 的 R6 寫的是 `cp`，才是實情。
實務上無害（`/tmp` 那份會自行消失），但兩份報告對同一個動作的描述不一致，而**紀錄準確度正是這個
專案的貨幣**。→ 把 CHANGE_REPORT 的「搬」改成「複製一份到」，或真的把 `/tmp` 那份刪掉。

**N-2（Low）— 三份文件對 `--build` 成本給了三個數字。**
plan rev 2 表格「24.6s → **27.9s**」、`CHANGE_REPORT` §9 與 commit message「24.6s → **26.5s**」、
本次獨立實測 **27.1s**。沒有人說謊，是 Pi 的負載雜訊，而 `VERIFICATION_REPORT.md` 的風險段已經
把話說對了（「不要把單一數字當成基準」）。→ 讓 plan 與 CHANGE_REPORT 指向那句話，
或統一寫成範圍，別再各持一個數字。

**N-3（Low，未驗證）— 「首次 lint 需要網路」這句話在 rev 2 之後可能已經不準。**
`--build` 讓**每一次** `make lint` 都經過一次 build，其中含 `load metadata for docker.io/library/python:3.12-slim`。
離線機器是否連暖機執行都會失敗，**本次未驗證**（我沒有安全的方式讓這台機器離線）。
→ 若在意，斷網跑一次 `make lint` 即可定論；否則把 `CHANGE_REPORT` §6 那句改成
「lint 每次執行都會走一次 build，離線行為未驗證」。

**N-4（Low，Round 1 我漏掉的）— plan 的 `Approval evidence` 欄位仍是未填的模板句。**
`IMPLEMENTATION_PLAN.md` 最後一行仍寫「**Not approved until a human explicitly records it here.**」，
而同一份文件上方已寫 `Status: Approved`、`Approved plan revision: 2`、`Approved by/date: jett / 2026-08-14`。
一個專門用來承載批准證據的欄位裡放著「尚未批准」的樣板句，讀者無法分辨「已批准」與「模板沒填」。
**rev 1 就是這樣，我 Round 1 沒看到，這是我的疏漏。** → 兩個 revision 各補一行實際的批准證據
（何時、以什麼形式），或刪掉模板句。

## 殘留風險（與 Round 1 相同，未因 rev 2 改變）

- **AC6 仍無 CI 實跑證據**，且 rev 2 自身也沒有。`--build` 對 CI 的影響（每次冷啟建置）同樣未量測。
  這是目前唯一還需要真實環境才能關掉的缺口——**開 PR 是關掉它的方法**。
- **AC8 的歸因仍是推論鏈**，不是對照實驗（本輪未重跑 `make test`，且我同意不需要重跑）。
- 本輪未執行：`make test`、`make eval`、`make format`、`make up`；未跨機器。

## Round 2 Human Disposition

三個 Medium 全部關閉：M1、L2、L4、L5 我**實測確認**，M2、L1、L3 為文件更正、已確認，
M3 是人類裁定、記載誠實。**沒有任何新的 Blocking / High / Medium。**
N-1 到 N-4 皆為紀錄準確度層級，可以現在修，也可以併入開 PR 前的最後一次整理。

The reviewer does not approve, fix, merge, or release this change.
**本報告不構成執行授權。**

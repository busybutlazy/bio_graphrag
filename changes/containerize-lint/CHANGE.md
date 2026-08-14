# Final Change: containerize-lint

對應 `docs/notes.md` N10（lint 的容器化入口，2026-08-13 由 `close-approve-item-backdoor` 第四輪獨立審查者提出，S-C）。

## Outcome

達成：`make lint` / `make format` 從「host 直接呼叫 ruff/mypy」改為容器化入口
（`docker compose run --rm lint`），使「lint 全過」成為審查者可在乾淨機器上獨立複核的宣稱，
而不再只能採信實作者自述。兩輪獨立審查（Round 1 對 plan rev 1、Round 2 對 rev 2 的 remediation）
皆已完成：**全程無 Blocking、無 High**；3 個 Medium（M1–M3）已修復或經人類明確裁定接受；
5 個 Low、3 個 Suggestion、Round 2 的 4 個記錄準確度 Low（N-1–N-4）均已處置。
已 commit 於分支 `feat/containerize-lint`（5 個 commit，`git log main..HEAD` 可查）；
**push 與 merge 尚未授權**。

## Consequential Behavior and Decisions

- lint/format 的命令與路徑單一來源集中在 `scripts/lint.sh`；`backend/Dockerfile` 新增獨立
  `lint` build stage（只裝 `requirements-dev.txt`，不進 runtime image）；`docker-compose.yml`
  新增 `lint` service（`profiles: ["tools"]`，`make up` 不會啟動）；CI lint job 移除 host 的
  `setup-python` + `pip install`。
- **D1（已定案，不建 ADR）**：lint 映像**不**疊在 backend runtime image 上，只裝 dev tooling，
  與現行 CI 環境完全等價，避免一次冒出大量既有 mypy 錯誤把「換執行方式」變成「修型別」。
  代價：mypy 對 fastapi / pydantic / asyncpg 仍走 `ignore_missing_imports`，型別訊號偏弱——
  這是現狀，不是本變更造成的退步，已記為 `docs/notes.md` **N13**，刻意延後，不在本次處理。
- **rev 2 修正（審查 M1、L4）**：
  - `make lint` / `make format` 改用 `docker compose run --build`，避免升級
    `requirements-dev.txt` 後本機靜默沿用舊映像、與每次冷啟建置的 CI 產生漂移。
  - `docker-compose.yml` 的 `backend` service 補 `target: runtime`，讓建置目標與
    `backend/Dockerfile` 的 stage 順序脫鉤（原本「lint stage 必須留在檔案最前面」只靠註解防守）。
- **偏差（皆經人類 jett，2026-08-14，明確裁定）**：
  - 既存 root-owned `.ruff_cache/`、`.mypy_cache/` 因 host 無法 `rm -rf`（root 所有），改以
    `docker compose run --rm --user 0:0 --entrypoint sh lint -c 'rm -rf /repo/.ruff_cache /repo/.mypy_cache'`
    刪除，繞過 plan 明列的「需要 sudo 即停止」stop condition。獨立審查（M3）指出
    `--user 0:0` + repo bind mount 在能力上等同 host sudo 對該路徑的寫入權。
    **人類裁定：接受本次，且不另立規則**——即這不成為未來同型 stop condition 的解讀先例。
  - 為判定 AC8（`make test`）失敗歸因，依人類明確指示執行 `docker compose down -v` 清空開發 volume。
    清空前已將未收錄進 seed 的治理資料（`curation_items` 20 列 `proposed`、
    `graph_change_logs` 24 列、`ingestion_jobs` 208 列）dump 出來；複製一份到 repo 外的持久位置
    `~/backups/bio_graphrag/2026-08-14-pre-wipe-governance-tables.sql`（是複製不是搬移，
    `/tmp` scratchpad 那份留給 session 自然清除）。**人類裁定：開發階段可接受此資料遺失**，
    `make seed` 已回填標準 demo 資料，站台功能正常。

## Verification and Review Disposition

- **AC1–AC7、AC9：PASS**（含 AC2 的負向對照——實際插入 ruff F401 與 mypy `[return-value]`
  缺陷，證明 `make lint` 真的會擋，兩者皆被兩輪審查獨立複現）。
- **AC8（`make test` 全綠）：字面未達標**。清空 volume 後 `1 failed, 241 passed`：唯一失敗
  `ingestion/tests/test_pipeline.py::test_qdrant_payload_is_queryable` 已完整歸因為
  「本機 `.env` 含 OpenAI key → 向量維度 1536 → 資料寫進 `biology_chunks_1536`，
  而測試硬編 `COLLECTION_NAME`（dim 128 的名字）」的既有不一致；
  實測 `biology_chunks` 0 點、`biology_chunks_1536` 9 點，審查獨立複現一致。
  與本變更 diff 無交集（未觸碰 `ingestion/`，runtime 映像內容未變）；CI（無 key）不受影響。
  依 `run-approved-change` 規則，未在驗證階段修它，已登記 `docs/notes.md` **N14**。
- **AC6（CI 免裝 host 套件）**：靜態證據成立，另在審查階段以 `git archive` 匯出的乾淨 checkout
  做了三個變體模擬（無 `.env`、無 `web` external network、`LINT_UID=1001` 非預設 uid）
  皆為 exit 0，把風險壓得很低。**但 CI 從未實際跑過**——這是唯一還需要真實環境才能關掉的缺口，
  開 PR 就是關掉它的方法。
- **兩輪獨立審查**（獨立 session，未繼承實作對話）：
  - Round 1：0 Blocking / 0 High / **3 Medium**（M1 build 快取永不重建、M2 diff base 已失效、
    M3 見上）/ 5 Low（報告矛盾、文件同步缺口、無關 commit 搭便車、stage 順序陷阱、
    備份只在 `/tmp`）/ 3 Suggestion（唯讀掛載、host 誤執行防護、uid fallback 靜默）。
  - Round 2（複核 rev 2 的 remediation）：**0 Blocking / High / Medium**。M1、L4、L5 經獨立實測確認；
    M2、L1、L3 為文件更正、已確認；M3 的記載方式被認可為誠實。4 個 Low（N-1–N-4）
    全屬紀錄準確度（「搬」該寫成「複製」、三份文件對同一耗時各持一個數字、
    「首次需要網路」的措辭在改用 `--build` 後可能不準、plan 的批准證據欄位仍是模板句），
    均已修正。
  - 完整逐項證據見 commit 歷史（`git show 6202a15:changes/containerize-lint/VERIFICATION_REPORT.md`、
    `git show 176e865:changes/containerize-lint/REVIEW_REPORT.md`），不在本檔重複抄錄。

## Durable Destinations

- `docs/notes.md` **N10** 狀態改為「已完成」，記載實際落地形態（本機沒有 `ruff`、`mypy` 版本
  也不對，比原始記載的現況更糟）。
- `docs/notes.md` **N13**（新）：mypy 對 runtime 套件真實型別的訊號偏弱，D1 刻意延後——後續 change。
- `docs/notes.md` **N14**（新）：`make test` 本機帶 OpenAI key 執行、與 `CLAUDE.md`「tests run
  offline」的宣稱不符，且暴露 `test_qdrant_payload_is_queryable` 對集合名稱硬編碼的既有缺陷——
  後續 change（需先定「測試該不該吃 `.env`」的姿態）。
- `CLAUDE.md` Commands 區塊：新增 `make lint` / `make format` 說明。

## Pending and Remaining Limitations

- **AC6**：CI lint job 從未實際跑過，只有靜態 + 乾淨 checkout 模擬證據——開 PR 是唯一能關掉
  此缺口的方法。
- **AC8**：既有失敗的歸因是推論鏈（diff 無交集 + volume 清空後轉綠 + Qdrant 點數實測），
  不是變更前後的對照實驗（未取得 baseline commit 上 `make test` 全套結果）。
- 只在單一 Raspberry Pi 上驗證，未跨機器。
- CI lint job 改用 `--build` 後冷啟動的耗時變化未量測（原本有 pip cache，現在每次冷啟 docker build，
  timeout 10 分鐘、僅裝兩個純 Python 套件，判斷寬裕但未實測）。
- 離線機器上暖機執行 `make lint` 的行為未驗證（`--build` 後每次都會經過一次
  `load metadata for docker.io/library/python:3.12-slim`）；這台機器同時對外服務，
  沒有安全的方式讓它斷網測試。
- `scripts/__pycache__`、`backend/app/**/__pycache__` 等既有 root-owned 檔案（由 `make test` 的
  backend 容器以 root 寫入）不在本次範圍，已於 N10 記載為既有問題、範圍更大。

## Rollback

```bash
git checkout -- Makefile docker-compose.yml backend/Dockerfile backend/requirements-dev.txt \
                .github/workflows/ci.yml CLAUDE.md docs/notes.md
rm -f scripts/lint.sh
docker image rm bio_graphrag-lint  # 若已 build
```

回滾後 `make lint` 恢復為 host 姿態（即變更前的壞狀態），無資料影響；已刪除的快取由工具自行重建。
已合併後則改用 `git revert`。

## Absorption Matrix

| Temporary information | Disposition | Durable destination or discard reason |
|---|---|---|
| N10 完成狀態與實際落地形態 | 已吸收 | `docs/notes.md` N10（實作 T6 完成） |
| D1 延後後果（mypy 型別訊號偏弱） | 已吸收 | `docs/notes.md` N13（實作 T6 完成） |
| AC8 既有失敗的完整歸因 ＋「本機測試花 token」發現 | 已吸收 | `docs/notes.md` N14（驗證階段記錄） |
| `make lint` / `make format` 使用方式變更 | 已吸收 | `CLAUDE.md` Commands 區塊 |
| M1–M3、L1–L5、N-1–N-4 審查處置細節與人類裁定 | 保留於本記錄 | 本檔 §Consequential Behavior、§Verification and Review Disposition；逐字證據仍可從 git 歷史（`6202a15`、`176e865` 等 commit）取得 |
| D1 / M3 是否值得 ADR 的評估 | 已處置 | 見下方 Decision Retention Packet；人類裁定不建立 ADR |
| CI 實跑證據缺口（AC6） | 未吸收，仍是限制 | 本檔 §Pending and Remaining Limitations；由「開 PR」關閉，非本次可關 |
| AC8 歸因是推論鏈非對照實驗 | 未吸收，仍是限制 | 本檔 §Pending and Remaining Limitations |
| 治理資料（curation_items / graph_change_logs / ingestion_jobs）清空前備份 | 已處置 | `~/backups/bio_graphrag/2026-08-14-pre-wipe-governance-tables.sql`（repo 外；內含真實治理資料，`data/seed/` 同類資產本就 gitignored，不入庫） |
| 5 份暫時報告本身（IMPLEMENTATION_PLAN / TASK_LOG / VERIFICATION_REPORT / REVIEW_REPORT / CHANGE_REPORT） | 內容已濃縮進本檔，原始檔已刪除 | 逐字內容仍可用 `git show <commit>:changes/containerize-lint/<file>` 取得（例如 `git show 176e865:changes/containerize-lint/CHANGE_REPORT.md`），不會真的遺失 |

## Decision Retention Packet

- **Candidate**：D1（lint 映像基底刻意不疊在 backend runtime image 上）
- **Why an ADR may be warranted**：涉及「型別檢查訊號強度 vs. 變更聚焦度」的取捨；未來若真要疊
  runtime image，會是一次獨立且需要處理既有錯誤的變更。
- **Existing durable coverage**：`docs/notes.md` N13 已完整記載決策、理由與延後範圍。
- **Alternatives evidenced**：選項 B（疊在 runtime image 上）的後果評估已在原 plan 的 D1 表格記載
  （現已隨舊檔刪除，內容摘要見上方 §Consequential Behavior）。
- **Recommendation**：Keep in Change Record
- **Human decision**：不建立 ADR（jett，2026-08-14）
- **ADR status**：none

- **Candidate**：M3（容器內 root 身分刪除 host root-owned 快取，是否構成繞過 sudo stop condition 的先例）
- **Why an ADR may be warranted**：觸及「container root + repo bind mount 在能力上等同 host sudo」
  這個一般化問題；獨立審查者明確提出「若默許可能建立不當先例」的疑慮。
- **Existing durable coverage**：本檔 §Consequential Behavior 已完整記載裁定與其明確不適用範圍。
- **Alternatives evidenced**：無——人類選擇的正是「就事論事，不歸納規則」本身，沒有需要對照的替代方案。
- **Recommendation**：Discard（人類已明確裁定範圍僅此一次；建 ADR 反而與該裁定的意圖矛盾）
- **Human decision**：不建立 ADR（jett，2026-08-14）
- **ADR status**：none

## Temporary Artifact Disposition

- **Delete after absorption**：`IMPLEMENTATION_PLAN.md`、`TASK_LOG.md`、`VERIFICATION_REPORT.md`、
  `REVIEW_REPORT.md`、`CHANGE_REPORT.md`——內容已濃縮進本檔；逐字內容仍可用
  `git show <commit>:changes/containerize-lint/<file>` 從 git 歷史取得，不會真的遺失，
  只是不再是工作目錄中的即時檔案。
- **Archive by explicit policy**：無。
- **Retain and reason**：本檔（`CHANGE.md`），本專案 `changes/containerize-lint/` 從此僅存此檔。

---

**說明（偏離既有慣例）**：本專案先前所有已結案的 change 目錄（例如
`close-approve-item-backdoor`、`ingest-concurrency-guard`）都保留完整 5 份報告，從未收斂成單一
`CHANGE.md`。本次改採 `close-change` skill 的預設收斂方式，是 2026-08-14 經人類明確選擇的結果
（非本 Agent 自行決定），詳見本次 close-change 對話。是否要讓後續 change 也比照辦理，
留待人類自行決定，本次不擴張為專案慣例變更。

# Coding Agent 自動化專案開發規範

適用於 Claude Code 與 Codex 的通用專案治理規範。此檔由 skill-forge 管理，請勿直接手改；要調整內容請修改 `canonical-configs/agent-guideline/guideline.md` 後重新安裝。

本文件是專案的**流程 source of truth**：`CLAUDE.md` / `AGENTS.md` 只保留永遠適用的短規則，完整流程與判斷標準以本文件為準。

---

## 一、責任分工

Agent 專案治理拆成以下層次，各司其職、互不取代：

```text
規格文件（SPEC / CONTRACTS）：要做什麼
Instruction file（CLAUDE.md / AGENTS.md）：永遠應遵守什麼
Skill：某類任務具體怎麼做
Hook：什麼動作必須發生或不得發生
CI：結果是否合格
Reviewer（獨立 agent 或人）：實作者是否漏掉問題
Human：是否批准繼續與接受成果
```

核心原則：**Agent 不得同時擁有「定義需求 → 自行擴張範圍 → 實作 → 驗證自己 → 批准自己完成」的完整鏈路。**

---

## 二、專案初始化階段

專案建立初期執行一次，後續持續維護。

### 1. 需求與驗收標準

定義專案目標、本階段範圍、明確不做的內容、功能與非功能需求、驗收條件、已知限制。

- 產物：`docs/SPEC.md`、驗收條件（可併入 SPEC 或獨立 `docs/acceptance-criteria.md`）。
- 規格描述**可觀察行為**，不直接指定所有實作。例：「輸入不合法時必須回傳明確錯誤，且不得寫入任何持久化資料。」

### 2. 架構邊界

定義模組組成、各模組責任與非責任、模組間通訊、資料與控制流向、錯誤處理層級、安全與一致性邊界。

- 產物：`docs/architecture/`、`docs/ADR/`。
- 重大技術決策記錄在 ADR（決策、替代方案、理由、後果）；一般實作細節不需要 ADR。

### 3. Contract

在前後端、模組或服務並行開發前，先定義：API request/response、RPC 或 event schema、錯誤碼、核心資料模型、認證欄位、timeout/retry/idempotency、相容性規則。

- 產物：`docs/CONTRACTS.md`、`schemas/`、`openapi/`、`proto/`。
- Contract 未確認前，不得讓多個 Agent 各自推測介面。

### 4. Walking Skeleton

先完成最小但完整的可執行路徑（入口 → application layer → mock adapter → 回傳），包含：可啟動、設定可載入、health check、logging、最小功能走完全程、基本測試、建置程序。不要一開始就並行做完所有模組。

### 5. CI 基線

CI 在大量業務邏輯進入前建立，且是**合併條件**，不只是報告工具。

- 最低限度：format check、lint、type check、unit test、build。
- 視專案增加：integration/contract/E2E test、migration check、dependency/secret/container scan。

---

## 三、開發循環（每次變更）

### 1. Change Request

每次變更先定義：要解決的問題、預期結果、In Scope、Out of Scope、驗收條件、限制與禁止事項。每個 change 有獨立識別名稱，產物放在 `changes/<change-id>/`（見第五節）。

不要下「完成整個下一階段」這種指令；改成單一功能、單一 use case、可獨立驗證的垂直切片。

### 2. 風險分級

| 等級 | 範例 | 自動化程度 |
|------|------|------------|
| 低 | 文件、註解、格式、局部測試補充 | 批准 Plan 後可使用 `supervised-auto` |
| 中 | 一般 API、業務邏輯、adapter 修改、一般重構、SDK 串接 | 審查並批准完整 Plan 後可使用 `supervised-auto` |
| 高 | 認證權限、DB migration、資料刪除、公開 Contract、金流、部署、production dependency | `one-task-at-a-time`，逐 Task 保留人工批准點 |
| 極高 | production 資料操作、secret/IAM、不可逆 migration、大量資料修改、全域安全策略 | manual only，不得使用 auto mode |

### 3. 唯讀現況分析

修改前必須：讀規格、Contract、ADR；找出相關程式碼與既有測試；確認目前行為與 Git 工作區狀態；記錄既有測試是否本來就失敗。

此階段**不得**：修改 production code、安裝 dependency、執行 migration、順手重構或修復無關問題。

### 4. Implementation Plan

產物：`changes/<change-id>/IMPLEMENTATION_PLAN.md`，至少包含：目標、In/Out of Scope、現況分析、受影響檔案、Contract/schema 影響、實作步驟、測試案例、風險與未知、rollback 方法、可獨立驗證的小 Task 清單，以及 Execution Policy（Plan revision、風險、`one-task-at-a-time` / `supervised-auto`、auto-approved Tasks、路徑範圍、人工 checkpoints 與 stop conditions）。

### 5. 人類批准計畫

人類確認：理解是否正確、有無過度設計、有無漏掉需求、有無動到不該動的區域、Task 是否夠小、測試策略是否合理、有無 breaking change、是否需要 migration 或 dependency。**未批准前不得進入正式實作。**

### 6. 先定義測試案例

實作前先列出正常、邊界、錯誤、權限、相容性、timeout/retry、資料一致性案例。不強制 TDD，但必須先知道「什麼結果才算正確」。

決策規則、權限判斷、狀態轉換、計算、validation 等 deterministic 邏輯優先寫 unit test；外部服務、DB、queue 補 integration test。

### 7. 依批准模式實作

預設 `one-task-at-a-time`：每次只執行批准計畫中的指定 Task，確認範圍 → 最小必要修改 → 更新測試 → 局部驗證 → 回報 → 停止等待下一個 Task。

低／中風險 Change 只有在人類明確批准目前 Plan revision 的 `supervised-auto`、auto-approved Task IDs 與路徑範圍後，才可依序連續執行。每個 Task 仍須局部驗證並寫入 `TASK_LOG.md`；需要新 Task／路徑／dependency／Contract 決定、觸發 checkpoint、發生不可歸因修改或完整驗證失敗時立即停止。完整驗證階段不得切回實作偷偷修正。

兩種模式都**不得**自行修改規格、擴張 scope、順手統一命名、順手更新 dependency、順手重構鄰近模組或刪除未確認的「看似未使用」程式碼。發現原計畫錯誤時，停止並回報，不得自行改寫需求。

### 8. 驗證與 Verification Report

依序執行 canonical commands（format → lint → type check → unit → integration → contract → E2E → build → security），記錄實際命令、exit code、通過/失敗數、未執行的測試與原因、是否使用 mock。**不得只寫「測試皆已通過」。**

產物：`changes/<change-id>/VERIFICATION_REPORT.md`，核心是 Requirement → Implementation → Test → Result 的追溯表，加上 Commands Executed、Tests Not Run、Known Risks、Human Review Hotspots。

### 9. Change Report

產物：`changes/<change-id>/CHANGE_REPORT.md`：完成內容、修改/新增/刪除檔案、外部可觀察行為變化、Contract/migration/dependency 變化、與計畫的偏差、breaking change、remaining work、rollback 方法。

報告必須同時揭露：**完成了什麼、沒完成什麼、沒驗證什麼、偏離了什麼、最不確定的是什麼。**

### 10. 獨立 Review

Reviewer（獨立 agent 或人）以唯讀方式嘗試**推翻完成聲明**：規格是否完整實作、測試是否真的對應需求（而非只測 mock）、錯誤路徑、相容性、安全、過度抽象、Out of Scope 修改、未證明的宣稱。Reviewer 不直接修改程式。

產物：`changes/<change-id>/REVIEW_REPORT.md`，finding 分級：Blocking / High / Medium / Low / Suggestion。

### 11. 人類最終審查與 Merge

人類優先閱讀：Plan、Change Report、Verification Report、Review Report、Contract diff、migration、dependency 變化、reviewer 標記的 hotspots，然後決定接受、要求修改、拆分、回退或拒絕。

合併前確認：CI 全過、必要 review 已批准、規格/Contract/ADR 已同步、migration 有 rollback、無 secret 或 debug code、commit 可理解可回退。部署後視需要做 smoke test、health check、指標監控與 rollback readiness。

---

## 四、哪些內容放在哪裡

### Instruction file（`CLAUDE.md` / `AGENTS.md`）

放每次工作都需要知道的長期規則：專案基本資訊、架構不變條件、Source of Truth 路徑表、canonical commands、高階開發流程、Stop Conditions、Definition of Done。

不放：大型報告模板、完整多步驟 procedure、單次任務需求、暫時進度、長篇教學。

> 判斷原則：每次工作都需要知道的放 instruction file；只有特定任務需要知道的放 Skill 或任務文件。

### Skills

封裝會重複執行的工作流程、檢查表、模板與 scripts。Agent 只在任務匹配時載入完整內容，適合承載比 instruction file 更長的程序。

skill-forge 已提供的 Change Workflow skills：

| Skill | 用途 | 禁止事項 |
|-------|------|----------|
| `deliver-roadmap-phase` | 使用者入口：指定一個 Roadmap Phase，拆分並協調受控 Changes | 推定下一 Phase、跨 Phase、自我批准、隱含 Git／release 動作 |
| `plan-change` | 唯讀分析、產生 Implementation Plan、拆 Task | 修改 production code、裝 dependency |
| `implement-task` | 只執行指定 Task、更新測試、回報偏差 | 自動執行下一 Task、擴張 scope |
| `run-approved-change` | 依批准 Plan 自動執行低／中風險 Tasks、驗證並報告 | 重規劃、自我 review／批准、commit／push |
| `verify-change` | 執行 canonical commands、建立追溯表、產生 Verification Report | 修改程式 |
| `report-change` | 比對 Plan 與實際 diff、產生 Change Report | 修改程式 |
| `review-change` | 唯讀審查、產生 Review Report | 修改程式 |
| `bootstrap-project` | 唯讀探索並在人工批准後建立 Docker-first 骨架、CI、canonical scripts | 未批准前不得寫入；不得使用 host fallback |

對 Roadmap 驅動的開發，使用者通常只需安裝並呼叫 `deliver-roadmap-phase`。安裝器會揭露並一併安裝它相依的 atomic Change Workflow skills；這些 skills 仍保持獨立，以便精準重跑單一 Task、驗證、報告或 review。入口 skill 不得降低任何底層 approval、risk、verification 或 authority gate。

`bootstrap-project` 是新專案缺少容器入口時唯一受規範允許的架設路徑：先唯讀探索並產生完整 bootstrap plan，取得人類對該計畫的明確批准後才能建立基線。在 Docker 基線完成前，不得在 host 安裝 dependency 或執行專案命令。

### Hooks

Hook 只做**確定性、快速、可機械判定**的事：危險命令阻擋（`rm -rf`、force push、不可逆 migration…）、保護檔案（`.env`、secrets、lock files、migration history）、修改後自動格式化、快速局部檢查、完成前檢查、通知與稽核。

不放：複雜架構審查、大型推理、完整 integration suite、會頻繁誤判的規則。

> 原則：Hook 做快速阻擋與自動化；CI 做完整驗證；Reviewer 做語意判斷。

skill-forge 的 `agent-hooks` guideline item 可為 Claude Code 與 Codex 安裝原生 `PreToolUse` 安全 hooks，阻擋明確的危險命令、直接在 `main`/`master` commit、host dependency 安裝，以及受保護路徑寫入（包含 notebook 編輯）。執行環境需要 `python3` 3.11 或更新版本；Codex 仍可能要求使用者信任精確的 hook definition。Hooks 是縱深防禦，不能取代 sandbox、權限、CI 或人工批准。

沒有受支援 lifecycle hook 的工具改用 git pre-commit/pre-push、task runner wrapper、sandbox policy 與 CI；目前 Windows launcher 與 Git fallback 尚未由 skill-forge 自動安裝。

### CI

最終的機器驗證與 merge gate。CI 不得依賴 Agent 自述、自然語言摘要或單一 reviewer agent 的判斷；Agent 報告只能引用 CI 結果，不能取代 CI。

### Subagents / Reviewer

用於角色與 context 隔離，並限制可用工具。建議角色：Explorer（唯讀搜尋）、Planner（只產生計畫）、Implementer（只執行指定 Task）、Code Reviewer / Security Reviewer / Test Reviewer（唯讀）。每個角色要有清楚的觸發條件、輸入輸出、工具限制與完成條件；不要建立過多角色。

### Permission / Sandbox

權限控制放在工具設定與執行環境，不是只寫在 Markdown。建議預設：

```text
讀取：允許 repository
寫入：只允許工作分支
網路：預設關閉或白名單
Production / Secret：禁止
Push、Merge、dependency install：人工批准
```

### Scripts / Task Runner

建立統一 canonical commands（如 `make setup / format / lint / typecheck / test-unit / test-integration / verify / build / run`），人類、Agent、CI 使用同一入口；instruction file 只列命令名稱，複雜內容放 script。

---

## 五、目錄約定

```text
repository/
├── CLAUDE.md / AGENTS.md        # skill-forge 納管的 agent memory
├── docs/
│   ├── agent-guideline.md       # 本文件（skill-forge 納管）
│   ├── agent-rules.md           # 專案特定規則與常用指令（專案自行維護）
│   ├── SPEC.md
│   ├── CONTRACTS.md
│   ├── ROADMAP.md
│   ├── architecture/
│   └── ADR/
├── changes/
│   └── <change-id>/
│       ├── REQUEST.md
│       ├── IMPLEMENTATION_PLAN.md
│       ├── VERIFICATION_REPORT.md
│       ├── CHANGE_REPORT.md
│       └── REVIEW_REPORT.md
├── .claude/                     # Claude Code：settings / hooks / agents / skills
├── .agents/skills/              # Codex：repository skills
├── scripts/
├── tests/
├── Makefile
└── .github/workflows/ci.yml
```

多 Agent 並用時：skill 名稱、報告模板、canonical commands、CI、instruction file 核心規則保持一致，避免兩套流程各自漂移。`changes/` 與 `docs/` 完全共用。

`changes/<change-id>/` 的用途是保存單次變更的決策、支援人類快速審查與 rollback 追蹤；完成後可歸檔，不需要載入每次 Agent context。

---

## 六、最低可行版本

不需要第一天就建立完整治理。最低限度：

```text
1. CLAUDE.md / AGENTS.md（agent memory）
2. 本文件（docs/agent-guideline.md）
3. plan-change / verify-change / report-change skills
4. make verify（或等價 canonical command）
5. CI
6. changes/<change-id>/
7. Git checkpoint（分支 + 可回退 commit）
```

再逐步增加：implement-task / run-approved-change skills、reviewer subagent、security review。若目標環境具備 Python 3.11+，可透過 guideline 安裝 protected-file / dangerous-command hooks。

---

## 七、最終原則

**Agent 可以自動化**：搜尋與分析、產生計畫、依批准 Execution Policy 實作 Task、新增測試、執行驗證、整理報告、提出 review findings、更新已批准的文件。

**Agent 不得自行決定**：改變需求、擴張 scope、修改公開 Contract、引入 production dependency、執行不可逆 migration、操作 production、存取 secret、忽略 failing test、批准自己的偏差、宣稱未證明的完成狀態、自行 merge 高風險變更。

整套流程濃縮為：

```text
規格 → 唯讀分析 → 實作計畫 → 人類批准 → 小 Task 實作
→ 機器驗證 → 變更報告 → 獨立審查 → 人類驗收 → CI 合併 → 部署驗證
```

Auto mode 只應存在於「已批准的輸入」與「不可跳過的驗證」之間，而不是涵蓋需求、規劃、實作、驗證與批准的全部流程。

<!-- skill-forge:agent-guideline version=0.7.0 sha256=4fa6fecea512d3c68571f0d6b2e0616c60e4905778ee776aa1bbcca0d02e7b58 -->

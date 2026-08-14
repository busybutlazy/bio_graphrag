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

先依第四節的 Project Lifecycle Routing 選擇入口：有未決選擇時使用 `grill-with-docs`；決策已具備 readiness evidence 時使用 `define-project`；只有取得 Human Project Approval 後，greenfield 專案才可進入 `bootstrap-project`。以下內容是各階段應建立的專案基礎，不代表 Agent 可以跳過入口 skill 的 admission、Decision Gates 或批准邊界。

### 1. 需求與驗收標準

定義專案目標、本階段範圍、明確不做的內容、功能與非功能需求、驗收條件、已知限制。

- 產物：`docs/SPEC.md`、驗收條件（可併入 SPEC 或獨立 `docs/acceptance-criteria.md`）。
- 規格描述**可觀察行為**，不直接指定所有實作。例：「輸入不合法時必須回傳明確錯誤，且不得寫入任何持久化資料。」

### 2. 架構邊界

定義模組組成、各模組責任與非責任、模組間通訊、資料與控制流向、錯誤處理層級、安全與一致性邊界。

- 產物：`docs/architecture/`、`docs/ADR/`。
- 重大技術決策才適合 ADR；一般實作細節不需要。Agent 只能提出 ADR candidate，必須先詢問人類是否值得建立；人類選擇 `Create ADR` 後才能草擬 `Proposed`，另一次明確確認後才能標記 `Accepted`、修改或 supersede 既有 ADR。

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

每次變更先定義：要解決的問題、預期結果、In Scope、Out of Scope、驗收條件、限制與禁止事項。每個 Change 有獨立識別名稱；進行中以單一 `changes/<change-id>/CHANGE_WORKING.md` 承載暫時資訊，結案後收斂為 `CHANGE.md`。

開發中發現有效但不屬於目前 scope 的問題，寫入受控的 `docs/PENDING.md`，包含 evidence、延後理由、可能後果、blocking trigger、owner 與來源。Pending capture 不授權實作，也不應偷偷擴張目前 Change。

不要下「完成整個下一階段」這種指令；改成單一功能、單一 use case、可獨立驗證的垂直切片。

### 2. 風險分級

| 等級 | 範例 | 自動化程度 |
|------|------|------------|
| 低 | 文件、註解、格式、局部測試補充、易回退局部修改 | 可使用 lightweight working record；依 repository policy 決定是否需獨立 Plan Approval |
| 中 | 一般 API、業務邏輯、adapter 修改、一般重構、SDK 串接 | 審查並批准完整 Plan 後可使用 `supervised-auto` |
| 高 | 認證權限、DB migration、資料刪除、公開 Contract、金流、部署、production dependency | `one-task-at-a-time`，逐 Task 保留人工批准點 |
| 極高 | production 資料操作、secret/IAM、不可逆 migration、大量資料修改、全域安全策略 | manual only，不得使用 auto mode |

### 3. 唯讀現況分析

修改前必須：讀規格、Contract、ADR；找出相關程式碼與既有測試；確認目前行為與 Git 工作區狀態；記錄既有測試是否本來就失敗。

此階段**不得**：修改 production code、安裝 dependency、執行 migration、順手重構或修復無關問題。

### 4. Risk-adaptive Working Plan

產物：`CHANGE_WORKING.md` 的 planning section。低風險只需目標、scope、acceptance、paths、verification 與 rollback；中高風險再加入 bounded tasks、checkpoints、Execution Policy、remediation envelope 與完整 traceability。不要複製 repository tour、動態行數、檔案數或 SHA 清單。

### 5. 依風險取得人類批准

Public Contract、schema/migration、權限/安全、不可逆或大量資料、production/外部花費、dependency/重大架構、高/極高風險或多個 consequential alternatives 必須取得明確批准。低風險是否需要獨立批准由 repository policy 決定。必要測試、文件同步、批准範圍內的一般修正與已接受 finding 的 bounded remediation 不自動使 Plan 失效。

### 6. 先定義測試案例

實作前先列出正常、邊界、錯誤、權限、相容性、timeout/retry、資料一致性案例。不強制 TDD，但必須先知道「什麼結果才算正確」。

決策規則、權限判斷、狀態轉換、計算、validation 等 deterministic 邏輯優先寫 unit test；外部服務、DB、queue 補 integration test。

### 7. 依批准模式實作

預設 `one-task-at-a-time`：每次只執行批准計畫中的指定 Task，確認範圍 → 最小必要修改 → 更新測試 → 局部驗證 → 回報 → 停止等待下一個 Task。

低／中風險 Change 只有在符合目前 Execution Policy 時才可連續執行。每個 outcome 將簡短 delta append 到 `CHANGE_WORKING.md`，不另外建立永久 `TASK_LOG.md`。驗證仍是 evidence-only；失敗後必須退出 verification，只有落在預先批准 remediation envelope 才能修復並重新驗證，否則停止。

兩種模式都**不得**自行修改規格、擴張 scope、順手統一命名、順手更新 dependency、順手重構鄰近模組或刪除未確認的「看似未使用」程式碼。發現原計畫錯誤時，停止並回報，不得自行改寫需求。

### 8. 驗證證據

依序執行 canonical commands（format → lint → type check → unit → integration → contract → E2E → build → security），記錄實際命令、exit code、通過/失敗數、未執行的測試與原因、是否使用 mock。**不得只寫「測試皆已通過」。**

驗證結果預設 append 到 `CHANGE_WORKING.md`，只有 audit policy 或人類明確要求才建立獨立 Verification Report。優先追溯 consequential acceptance；任何會花費、修改 persistent data、使用 secret 或接觸 production 的驗證命令都要預先取得權限。

### 9. Review Handoff

在同一份 working record 中準備 concise Review Handoff：diff base、completion claim、外部行為、material effects、偏差、未驗證、限制、rollback、Pending candidates 與可能的 ADR candidates。引用既有 evidence，不複製命令表與 task history。

### 10. 獨立 Review

Reviewer（獨立 agent 或人）以唯讀方式嘗試**推翻完成聲明**：規格是否完整實作、測試是否真的對應需求（而非只測 mock）、錯誤路徑、相容性、安全、過度抽象、Out of Scope 修改、未證明的宣稱。Reviewer 不直接修改程式。

產物：單一 `changes/<change-id>/REVIEW.md`，以穩定 finding ID 與狀態維護，不建立 `_2`、`_3` 等副本。預設一次完整 review 加一次 accepted findings 的 targeted confirmation；只有 remediation 改變重要行為或風險面才重開完整 review。純 working metadata／表頭／行數問題原則上不是產品 finding。

### 11. Closure、Retention 與人類接受

人類先 disposition findings；remediation 後由 reviewer targeted confirmation。接著在 fresh closure context 執行 `close-change`：建立 Absorption Matrix，把 temporary knowledge 放入 durable project truth、Pending、final `CHANGE.md` 或明確 discard reason。

所有 ADR candidates 必須組成 Decision Retention Packet，逐項詢問人類：Create ADR / Keep in Change Record / Defer to Pending / Discard。刪除 temporary artifact 永遠不授權 agent 自動建立 ADR。

Absorption 與 retention 完成後，才可提出刪除或 archive `CHANGE_WORKING.md`；最後停在 Human Change Acceptance。Reviewer 可做一次 closure-integrity check，但不得因此重開完整 code review。

合併前確認：CI 全過、必要 review 已批准、規格/Contract/ADR 已同步、migration 有 rollback、無 secret 或 debug code、commit 可理解可回退。部署後視需要做 smoke test、health check、指標監控與 rollback readiness。

---

## 四、哪些內容放在哪裡

### Instruction file（`CLAUDE.md` / `AGENTS.md`）

放每次工作都需要知道的長期規則：專案基本資訊、架構不變條件、Source of Truth 路徑表、canonical commands、高階開發流程、Stop Conditions、Definition of Done。

不放：大型報告模板、完整多步驟 procedure、單次任務需求、暫時進度、長篇教學。

> 判斷原則：每次工作都需要知道的放 instruction file；只有特定任務需要知道的放 Skill 或任務文件。

### Skills

封裝會重複執行的工作流程、檢查表、模板與 scripts。Agent 只在任務匹配時載入完整內容，適合承載比 instruction file 更長的程序。

#### Human-friendly Workflow Entrypoints

一般使用者主要記住以下入口：

| 入口 | 用途 |
|------|------|
| `what-next` | 依 repository evidence 說明目前狀態、下一個入口與下一道 gate |
| `work-on-change` | 推進一個 bounded Change，並自行選用適合的 atomic Change Workflow skill |
| `work-on-phase` | 推進一個指定且唯一的 Roadmap Phase |
| `review-change` | 在新開、乾淨的 agent context 中進行獨立對抗式審查 |
| `triage-pending` | 分類延後發現、檢查 blocking trigger，不實作或代替人類決策 |
| `close-change` | 收斂 temporary artifacts、執行 Human ADR Retention Gate、產生 final `CHANGE.md` |

安裝時，`what-next` 是 Development Workflow bundle 的根節點，會一併安裝上述入口與相關 atomic skills。安裝完整 dependency closure 只代表 workflow 可用，不代表入口取得跨越 Human Approval、review、Git 或 release boundary 的權限。

正式 `review-change` 必須由未繼承 implementation conversation 的全新 agent／session 執行。同 context 的自我檢查不能產生滿足正式 gate 的 Review Report；subagent 只有在平台保證不繼承該 conversation 時才具備正式 reviewer 的獨立性。

#### Project Lifecycle Routing

這張表只選擇入口，不取代各 skill 的 admission、approval 或 authority 規則。並非所有專案都必須先執行 `grill-with-docs`；決策已完整時直接進入相應下游入口。

| 情境 | 路由 |
|------|------|
| Unsure where the repository is | `what-next` → evidence-based routing |
| New or ambiguous project | `what-next` → `grill-with-docs` → `define-project` → human project approval → `bootstrap-project` |
| Ambiguous or clear bounded change | `work-on-change` → applicable decision/change atomic skills → independent `review-change` |
| Approved Roadmap phase | `work-on-phase` → `deliver-roadmap-phase` → human phase acceptance |

入口判斷：

- 模糊或有重大未決策：`grill-with-docs`。
- 決策已完整但尚未形成正式專案文件：`define-project`。
- 已有人類批准的 Project Definition，但缺開發基線：`bootstrap-project`。
- 已批准 Roadmap 且準備交付一個明確 Phase：使用 `work-on-phase`，由它路由至 `deliver-roadmap-phase`。

`grill-with-docs` 必須保存完整或明確標示 partial 的 Decision Inventory。只有 `Status: Ready` 且 `Blocking Open Decisions: None` 可進入 `define-project` 或 `plan-change`；已完成評估但存在 blockers 使用 `Stopped With Blocking Decisions`，尚未完成 inventory 或 readiness assessment 則使用 `Incomplete — Session Stopped Before Readiness Assessment`。

skill-forge 已提供的 Workflow skills：

| Skill | 用途 | 禁止事項 |
|-------|------|----------|
| `what-next` | 從 durable truth、Pending、working record、review 與 closure evidence 判斷下一步 | 猜測批准、讓 unrelated Pending 阻擋工作、重建已吸收刪除的暫時報告 |
| `work-on-change` | 推進一個 bounded Change，依 artifacts 選擇適合的 atomic workflow；預設一次一個 workflow | 自我批准、同 context 自我 review、隱含 Git／release 動作 |
| `work-on-phase` | 人類入口：指定一個 Roadmap Phase，轉交底層 phase delivery workflow | 推定下一 Phase、跨 Phase、降低底層 admission 或 authority gate |
| `grill-with-docs` | 盤點所有未決選擇、分類決策 ownership，並優先收斂 load-bearing decisions | 遺漏影響 observable behavior／failure handling／data semantics／operations／acceptance 的小型選擇；production implementation；自行批准決策 |
| `define-project` | 將具備 readiness evidence 的決策整理為可批准的 SPEC、必要 CONTRACTS 與含 Decision Gates 的 outcome-based ROADMAP | 猜測未決策答案、把不安全的延後事項視為 ready、自行批准或啟動 bootstrap |
| `deliver-roadmap-phase` | `work-on-phase` 使用的底層 orchestrator：拆分並協調指定 Phase 的受控 Changes | 推定下一 Phase、跨 Phase、自我批准、隱含 Git／release 動作 |
| `plan-change` | 建立 risk-adaptive `CHANGE_WORKING.md`，納入 relevant Pending 與 remediation envelope | 修改 production code、裝 dependency |
| `implement-task` | 只執行指定 Task、append concise evidence、capture Pending | 自動執行下一 Task、擴張 scope |
| `run-approved-change` | 在批准 envelope 內執行低／中風險 outcomes、驗證並準備 handoff | 重規劃、自我 review／批准、commit／push |
| `verify-change` | 執行 canonical commands，將 consequential evidence 寫入 working record | 在 verification mode 修改程式 |
| `report-change` | 相容入口：更新 working record 的 Review Handoff | 產生重複的 final report、修改程式 |
| `review-change` | Fresh review，以一份 `REVIEW.md` 與 stable IDs 管理 findings | 修改程式、無限重開 cosmetic review |
| `triage-pending` | 驗證與分類 Pending destinations／blocking triggers | 自行選擇解法或實作 |
| `close-change` | Absorption、Human Retention Gate、final `CHANGE.md` 與 temporary disposal | 自行接受 ADR、重新 review 或修改程式 |
| `bootstrap-project` | 唯讀探索並在人工批准後建立 Docker-first 骨架、CI、canonical scripts | 未批准前不得寫入；不得使用 host fallback |

一般使用者通常只需從 manager 安裝 Development Workflow，並呼叫 `what-next`、`work-on-change`、`work-on-phase` 或在新 agent 中呼叫 `review-change`。底層 skills 仍保持獨立，以便入口路由與精準重跑單一 Task、驗證、報告或 review。入口 skill 不得降低任何底層 approval、risk、verification 或 authority gate。

`work-on-change` 的建議互動邊界是每次只執行一個 atomic workflow，回報新的 state 與 next action 後交還控制權。這不是硬性禁止串接：只有入口要求明確授權連續範圍，且相鄰 workflows 之間不存在新的 Human Approval、decision、checkpoint、independent review、Git、release 或 deployment authority gate 時，才可在每次重新驗證 admission criteria 後繼續。

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

用於角色與 context 隔離，並限制可用工具。建議角色：Explorer（唯讀搜尋）、Planner（只產生計畫）、Implementer（只執行指定 Task）、Code Reviewer / Security Reviewer / Test Reviewer（唯讀）。每個角色要有清楚的觸發條件、輸入輸出、工具限制與完成條件；不要建立過多角色。一般 reviewer subagent 可提供自我檢查證據，但若平台不能保證它未繼承 implementation conversation，就不能滿足正式獨立 review gate。

#### 委派政策

任務複雜度依影響範圍、風險、所需探索量與可獨立分工性判斷，不得只用修改行數判斷：

| 複雜度 | 判斷方式 | 執行方式 |
|--------|----------|----------|
| 簡單 | 單一局部、低風險、行為明確、無需廣泛探索或跨模組協調 | 主 agent 可直接執行 |
| 中等 | 涉及多個檔案、一般業務邏輯、測試面向或需要先探索既有行為 | 若有邊界清楚且可獨立驗證的子工作，應委派至少一項給 subagent |
| 複雜 | 跨模組／服務、探索輸出龐大、多種驗證面向或需要獨立 review | 應拆成多個有界子工作，優先使用 subagents；只有相依的關鍵路徑留在主 agent |

適合委派的工作包括：唯讀 codebase 探索、規格或文件查證、測試執行與失敗分析、log 分析、互不重疊的實作 Task，以及獨立 code／security／test review。委派的目的除了平行化，也包括把搜尋結果、測試輸出、stack trace 與探索筆記隔離在子 context，讓主 context 專注於需求、限制、決策與最終成果。

每次委派必須遵守：

1. 主 agent 明確提供目標、範圍、必要背景、允許的工具／寫入邊界、預期輸出與完成條件。
2. 子工作必須可獨立完成與驗證；不要把仍需共同決策或高度耦合的工作硬拆出去。
3. 多個寫入型 subagent 不得同時修改相同或高度重疊的檔案；寫入範圍不易隔離時改為循序執行，或只委派唯讀分析。
4. subagent 回傳的是證據與建議，不是自動成立的完成聲明。主 agent 必須檢查關鍵結論、整合變更、處理衝突並執行最終驗證。
5. 不得用委派繞過 Human Approval、Execution Policy、sandbox、Stop Conditions、獨立 review 或其他 authority boundary。
6. 若環境不支援 subagent，或任務沒有合理的獨立子工作，主 agent 可自行執行，但應限制載入內容並摘要大量中間輸出；中等或複雜任務還應在回報中簡述未委派原因。

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
│   ├── PENDING.md
│   ├── architecture/
│   └── ADR/
├── changes/
│   └── <change-id>/
│       ├── CHANGE_WORKING.md     # temporary
│       ├── REVIEW.md             # stable finding IDs
│       └── CHANGE.md             # durable after closure
├── .claude/                     # Claude Code：settings / hooks / agents / skills
├── .agents/skills/              # Codex：repository skills
├── scripts/
├── tests/
├── Makefile
└── .github/workflows/ci.yml
```

多 Agent 並用時：skill 名稱、報告模板、canonical commands、CI、instruction file 核心規則保持一致，避免兩套流程各自漂移。`changes/` 與 `docs/` 完全共用。

`CHANGE_WORKING.md` 與中間 Phase/decision packets 是 temporary artifacts。只有完成 Absorption Matrix、Pending capture 與 Human ADR Retention Gate 後才能刪除或 archive；`CHANGE.md` 保存最後仍影響未來工作的結果與限制。

---

## 六、最低可行版本

不需要第一天就建立完整治理。最低限度：

```text
1. CLAUDE.md / AGENTS.md（agent memory）
2. 本文件（docs/agent-guideline.md）
3. Development Workflow bundle（以 `what-next` 安裝完整 dependency closure）
4. make verify（或等價 canonical command）
5. CI
6. changes/<change-id>/
7. Git checkpoint（分支 + 可回退 commit）
```

再逐步增加：更細緻的 project-specific hooks、專門 security review、外部 approval receipt 與 CI policy enforcement。若目標環境具備 Python 3.11+，可透過 guideline 安裝 protected-file / dangerous-command hooks。

---

## 七、最終原則

**Agent 可以自動化**：搜尋與分析、產生計畫、依批准 Execution Policy 實作、新增測試、執行驗證、capture Pending、提出 review findings、更新已批准的 durable 文件、整理 ADR candidates。

**Agent 不得自行決定**：改變需求、擴張 scope、修改公開 Contract、引入 production dependency、執行不可逆 migration、操作 production、存取 secret、忽略 failing test、批准自己的偏差、把 candidate 升格為 Accepted ADR、宣稱未證明的完成狀態、自行 merge 高風險變更。

整套流程濃縮為：

```text
規格／Pending／ADR → risk-adaptive working plan → 必要的人類批准 → 有界實作
→ 機器驗證 → fresh review → 人類 disposition → targeted confirmation
→ absorption + Human ADR Retention Gate → durable CHANGE.md → 人類驗收 → Git／部署
```

Auto mode 只應存在於「已批准的輸入」與「不可跳過的驗證」之間，而不是涵蓋需求、規劃、實作、驗證與批准的全部流程。

<!-- skill-forge:agent-guideline version=0.8.5 sha256=857d309292b1b4be79f54253259273b859559f2726d5815c352890976ab491b5 -->

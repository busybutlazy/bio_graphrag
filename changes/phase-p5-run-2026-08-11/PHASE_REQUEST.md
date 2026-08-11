# Phase Request: P5 — 停在 Phase Readiness Gate

- **Phase run id:** `phase-p5-run-2026-08-11`
- **Roadmap 路徑:** `changes/unified-two-gate-review/IMPLEMENTATION_PLAN.md` §Roadmap
- **Phase ID:** `P5`（唯一匹配,無歧義）
- **Repo 狀態:** `main` @ `0a3e5be`（PR #16 已合併),工作區乾淨
- **狀態:** **NOT ADMITTED —— 停止並路由至 `grill-with-docs`**

## Phase 原文（逐字）

> - **P5:** gold as `back_translation` regression + live schema-gap backlog (D2); per-group staging in the
>   real extract path.

同一份計畫的 Out of Scope（`:31`）另有一句措辭略異的版本:
「gold/backlog repurpose (D2); per-group staging in the real LLM extract path」。

## 為什麼不能進入 planning

Phase Readiness Gate 要求 phase 具備**已批准的 observable outcome、scope、acceptance criteria 與
Decision Gates**。P5 是一行 bullet:沒有驗收條件、沒有可觀察產出定義、沒有任何 Decision Gate。
更關鍵的是,其核心內容是一個**尚未決定的重大架構選擇**,依 skill 規定不得在 phase delivery 內以
假設解決。

Roadmap 自己也記載此事被**刻意延後**且**會在此時成為阻擋**:

- `unified-two-gate-review/IMPLEMENTATION_PLAN.md:154` — R3:「real-extract grouping is **deferred**
  (becomes blocking when the real pipeline lands)」
- `two-gate-review-p3/IMPLEMENTATION_PLAN.md:234` — 「Extract path still ungrouped (accepted, P5)」

也就是說:延後條款的觸發條件現在到了,但**延後的那個決定從未被做出**。

## 現況證據（唯讀探索）

**抽取路徑目前如何 staging**（`ingestion/pipeline/load_postgres.py:109 stage_extraction_output`,
由 `ingestion/extract/runner.py:262` 逐 chunk 呼叫）:

- 每個 node/edge 各寫**一列** `curation_items`,`proposed_by='llm'`
- `item_id = f"curation:{node['id']}"` —— **全域命名**,非群組範圍
- **完全沒有寫 `group_id`** → `list_groups`（只取 `group_id IS NOT NULL`)永遠看不到它們
- `ON CONFLICT (item_id) DO NOTHING` → 同一個概念跨 chunk / 跨文件重複抽出時,**全域去重成一列**

對照已群組化的兩條路徑:`stage_demo_review_group` 與 `service.create_group` 都用
`item_id = f"curation:{group_id}:{elem_id}"`。

## 阻擋的決定（需要人類裁決,不得由執行者假設）

### G1 —— 抽取路徑的「一個群組」是什麼？（重大架構選擇）

這定義了**人類審閱的單位**,也就是本專案治理敘事的核心原語。候選:

| 選項 | 規則 | 代價 |
|---|---|---|
| a | 一個 chunk = 一個群組 | 最簡單;但一個 chunk 常含多個不相關陳述,專家被迫全收或全退 |
| b | chunk 產出圖的**連通元件** = 一個群組 | 無需改 prompt;但連通不等於「同一個陳述」（共用概念會把不相關陳述黏成一團) |
| c | 一個 **pattern instance**（RegulatoryEffect 三段式 / Interaction) = 一個群組,其餘各自成組 | 最貼合 `engineer_gate._pattern_check` 與 `back_translation` 的既有語意;需定義「其餘」怎麼歸 |
| d | **由 LLM 明確輸出分組** | 語意最準;但要改 `prompts/` 與 `schema/extraction_output_schema`——**這是 contract 變更** |

### G2 —— item_id 方案與去重語意（與既有 guard 直接衝突）

若改用群組範圍 `curation:{group_id}:{elem_id}`,全域去重就消失:同一個概念（例如「胰島素」）
出現在 3 個陳述裡會變成 3 列、分屬 3 個群組。

**這會撞上 `approve_group` 既有的 B1 guard**:核准群組 A 寫入「胰島素」後,群組 B 含同一個
`hormone:insulin` 會命中「成員 id 已存在於 approved 圖」→ **409,永遠無法核准**
（`docs/api_contract.md` 該表第 5 列）。

現有的手工路徑已有可借鑑的作法:`create_group` 讓 edge 端點**引用**既有 approved 節點而非重新提案。
但「抽取路徑何時該引用、何時該提案」需要一條明確規則,且會影響跨 chunk 的行為。這是一個
**資料所有權 / 去重語意決定**,不是實作細節。

### G3 —— 跨 chunk 的陳述

一個生物陳述可能被切在兩個 chunk。分組是否一律限縮在單一 chunk 內？若否,`runner.py` 的逐 chunk
迴圈結構要改（目前 staging 發生在迴圈內、逐 chunk commit)。

### G4 —— P5 的第二個產出「live schema-gap backlog (D2)」本身有未決決定

`REVIEW_REPORT.md` 的 L2／L3 處置明確把以下項目留給這個 backlog 變更決定,至今未決:

- gap 的 accept / reject / **復原** 生命週期（L2:非 demo 來源目前不可逆)
- `possible_schema_gap` 旗標的**有稽核 engineer override**（L3:誤勾即永久無法核准)
- `data/sample/expert_demo/schema_gap_backlog.json` 的去留（S3)

### G5 —— P5 的第一個產出可能已完成，phase 邊界待確認

「gold as `back_translation` regression」看來已存在:`backend/tests/gold/test_gold_examples.py`
（6 tests,全綠),其 docstring 自陳「MVP 先打 cases.json 裡的固定 proposal;未來換真 pipeline 時,
gold 從『打固定 proposal』切成『打真實抽取輸出』」。

也就是說這一項**部分完成**:regression 網存在,但「打真實抽取輸出」那一半與 G1 綁在一起。
需要 owner 確認 P5 此項的完成定義。

## 建議的最小人類決定

依 skill 規定路由至 **`grill-with-docs`**,議題限定為 G1／G2／G3（抽取路徑的群組化語意）。
G4 屬 P5 的另一個子產出,建議**拆成獨立 phase 或獨立 change**,不與抽取路徑綁在同一次交付——
兩者唯一的關聯只是同列在一行 roadmap bullet 上。

在 G1／G2 決定之前,任何實作都會是對「人類審閱單位」這個治理核心原語的猜測。

## 執行者狀態聲明

本次僅做唯讀探索,未修改任何實作檔。唯一寫入為本檔（planning artifact)。
未執行任何專案指令（未跑測試、未動資料庫)。Phase 狀態未推進。

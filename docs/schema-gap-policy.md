# Schema Gap Policy — 白話 ⇄ code 映射

> 對應 `docs/expert-in-the-loop-plan.md` 五.6。
> 專家**不需要知道內部 gap code**。專家畫面只呈現白話選項,系統內部再映射成
> `schema_gap_type`,並寫入 `data/sample/expert_demo/schema_gap_backlog.json`。

## 為什麼需要這份 policy

工程師 gate 管形式、專家 gate 管意義。當專家發現「系統理解」漏掉或扭曲了原文的
核心生物語意,而**現行 schema 根本沒有對應 pattern 可表達**時,這不是 bug,而是一個
schema gap。專家用白話標記它;此表把白話標記翻成內部 `schema_gap_type`,讓 gap 成為
可追蹤、可排期、可演進的工程資產,而不是消失在註解裡。

## 白話選項 ⇄ `schema_gap_type`

| 專家看到(白話) | `schema_gap_type` |
|---|---|
| A 不是直接影響 C,而是改變 B 對 C 的作用強度 | `permissive_effect` |
| A 和 B 之間不是因果,而是拮抗/協同 | `antagonistic_or_synergistic_interaction` |
| 這是一個多步驟調控路徑,不是單一效果 | `pathway_or_cascade` |
| 這是一個條件式效果,需要特定前提才成立 | `conditional_effect` |
| 這是一個閾值效果 | `threshold_effect` |
| 其他 | `unknown` |

## Backlog 資料結構

每筆 `schema_gap_backlog.json`:

| 欄位 | 說明 |
|---|---|
| `gap_id` | 穩定識別碼 |
| `raised_by_case` | 觸發此 gap 的案例 id(通則型可為 `null`) |
| `schema_gap_type` | 上表映射結果 |
| `expert_facing_reason` | 專家看得懂的白話理由 |
| `example_text` | 觸發的原文例句 |
| `status` | `backlog` \| `proposed` \| `accepted` \| `rejected` |
| `proposed_schema_change` | 若要補 schema 的初步方向 |
| `raised_at` | 提出日期 |

## MVP 排除但入 backlog 的型別(D6)

以下型別在 MVP **不實作**,只記 backlog:`CellType`、`Stimulus`、`STIMULATES`、
`AntagonisticInteraction`、`ON_PROCESS`(以及軟性 backlog 的 `ACTS_VIA`)。
能用現行 schema 合理對齊的先對齊(見計畫 D1–D5),只有真的表達不了的才當硬 gap
——目前唯一的硬 gap 是 Case 5 的 `permissive_effect`。

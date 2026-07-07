# LLM Extraction Guidelines

Schema(`node_types.md`、`relationship_types.md`)定義了「有哪些節點/關係類型」,但不足以讓 LLM 決定「這句話該不該產生一個節點,產生哪一種」。本文件是給 extraction agent 的獨立判斷準則,對應 `docs/graph_plan.md` 2.4 節「LLM 只負責提案」的原則。

## 總原則

- LLM 的輸出永遠是 `proposed` 狀態的候選節點/關係,不直接寫入 approved graph。
- 每個候選節點/關係都必須帶 `source_chunk_id`,標明是從哪段文字抽出來的——沒有來源就不要生成。
- 不確定的內容寧可不生成,也不要用低信心的猜測填滿 graph。schema 允許的類型,不代表每次都要用滿。
- 輸出必須是單一 JSON 物件,結構完全符合 `extraction_output_schema.json`;不符合 schema 的輸出視為失敗,不會進入 `curation_items`。

## 什麼時候建立 RegulatoryEffect

`RegulatoryEffect` 是 fact node,只在文本明確描述「誰對什麼生理變因造成什麼方向的效果」時建立,例如:

> 胰島素會降低血糖濃度。

→ 建立一個 `RegulatoryEffect`(`insulin_decreases_blood_glucose`),並用 `HAS_EFFECT`(Hormone -> RegulatoryEffect)與 `ON_VARIABLE` + `DECREASES`(RegulatoryEffect -> PhysiologicalVariable)連接。

**不要**跳過 RegulatoryEffect,直接寫 `Insulin -> DECREASES -> Blood glucose`——這會遺失「這是一個可獨立驗證的事實節點」的結構,也讓後續 Interaction/FeedbackLoop 無法引用這個事實。

## 什麼時候建立 Interaction

當文本描述兩個(或以上)`RegulatoryEffect` **同時作用在同一個 `PhysiologicalVariable`** 上,且彼此方向相反或相輔相成時,建立一個 `Interaction` 節點,用 `USES_EFFECT` 連接它引用的每個 `RegulatoryEffect`:

- 方向相反(一個 `INCREASES`、一個 `DECREASES`)→ `interaction_type: antagonism`。
- 方向相同、且描述為「共同增強」→ `interaction_type: synergism`。

不要在還沒有至少兩個對應的 `RegulatoryEffect` 之前就建立 `Interaction`——`Interaction` 永遠是引用既有事實節點的組合,不能無中生有。

## 什麼時候建立 FeedbackLoop

當一組 `RegulatoryEffect` 構成一個閉環——某個效果最終會回頭影響觸發它自己的變因——才建立 `FeedbackLoop`,用 `USES_EFFECT` 連接迴路中涉及的 `RegulatoryEffect`,並判斷:

- 效果會抑制原本觸發它的變化 → `feedback_type: negative`。
- 效果會放大原本觸發它的變化 → `feedback_type: positive`。

文本只描述單一方向的效果、沒有描述「回頭影響」的閉環時,不要建立 `FeedbackLoop`,建一個 `RegulatoryEffect` 即可。

## Misconception 的建立時機

只在文本明確指出「這是一個常見錯誤觀念」或提供了對照的正確概念時建立 `Misconception`,並用 `COMMONLY_CONFUSED_WITH` 或 `CAUSES`/其他適當關係連回正確概念,不要自行揣測學生可能會怎麼誤解。

## 命名與去重

- 新節點 `id` 一律遵守 `node_types.md` 的 `<type_prefix>:<snake_case_name>` 慣例。
- 生成前先檢查是否已有語意相同的節點(即使命名不同),若懷疑重複,仍然生成候選節點,但在 `payload` 附上 `possible_duplicate_of` 欄位,交由人工在 curation 階段決定是否 merge——LLM 不自行判斷合併。

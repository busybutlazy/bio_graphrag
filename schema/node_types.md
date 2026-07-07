# Node Types

適用範圍:sample biology graph(激素調控主題),對應 `docs/graph_plan.md` 4.1 節。

## ID 慣例

所有節點一律使用字串 `id` 屬性作為對外識別碼,不依賴 Neo4j 內部 id。格式為 `<type_prefix>:<snake_case_name>`,例如:

```text
concept:homeostasis
hormone:insulin
receptor:insulin_receptor
physiological_variable:blood_glucose
regulatory_effect:insulin_decreases_blood_glucose
interaction:insulin_glucagon_blood_glucose
feedback:blood_glucose_negative_feedback
```

## 共同屬性

每個節點都必須有:

| 屬性 | 型別 | 說明 |
|---|---|---|
| `id` | string | 對外識別碼,見上方慣例 |
| `type` | string | 節點類型,對應下表 |
| `label` | string | 顯示名稱,例如 `Insulin` |
| `status` | string | `proposed` / `approved` / `rejected` / `deprecated` / `merged`,預設 `proposed` |
| `description` | string | 一到兩句說明 |

`status` 由 curation workflow 控管,只有 `approved` 節點會進入 retrieval(見 `graph_schema.md`)。

## Node Type 列表

| Node Type | 用途 | 範例 |
|---|---|---|
| Concept | 一般概念 | Homeostasis、Photosynthesis |
| System | 生物系統 | Endocrine system、Immune system |
| Process | 生理或分子流程 | Glycolysis、Negative feedback |
| Structure | 結構 | Pancreas、Mitochondria |
| Molecule | 分子 | Insulin、Glucose、ATP |
| Hormone | 激素 | Glucagon、ADH |
| Receptor | 受器 | Insulin receptor、ADH receptor |
| PhysiologicalVariable | 被調控的生理變因 | Blood glucose、Blood osmolarity、Blood calcium |
| RegulatoryEffect | **Fact node(事實節點)**:某個調控者對某個生理變因造成的單一效果事實 | Insulin lowers blood glucose |
| Interaction | 兩個或多個激素效果如何共同影響同一個生理變因(拮抗/協同) | Insulin and glucagon antagonism on blood glucose |
| FeedbackLoop | 回饋迴路 | Blood glucose negative feedback loop |
| Enzyme | 酵素 | Amylase、DNA polymerase |
| Disease | 疾病或異常 | Diabetes mellitus |
| Experiment | 經典實驗 | Hershey-Chase experiment |
| Misconception | 常見錯誤觀念 | Insulin directly digests glucose |

## 額外屬性

`Interaction` 節點需標示交互作用類型:

```json
{
  "id": "interaction:insulin_glucagon_blood_glucose",
  "type": "Interaction",
  "interaction_type": "antagonism",
  "scope": "blood_glucose_regulation"
}
```

`FeedbackLoop` 節點需標示正/負回饋:

```json
{
  "id": "feedback:blood_glucose_negative_feedback",
  "type": "FeedbackLoop",
  "feedback_type": "negative",
  "regulated_variable": "blood_glucose"
}
```

`interaction_type` 允許值:`antagonism`、`synergism`。
`feedback_type` 允許值:`positive`、`negative`。

## Fact Node 與高階解釋節點的區分

`RegulatoryEffect` 是本 schema 唯一的 **fact node**:每個 `RegulatoryEffect` 對應文本中一句可驗證的調控事實(誰對什麼生理變因造成什麼方向的效果),是 `Interaction` 與 `FeedbackLoop` 組合的最小單位。

`Interaction`、`FeedbackLoop` 不是 fact node,而是**高階解釋節點**——由多個 `RegulatoryEffect` 組合而成,說明這些事實之間如何共同運作(拮抗、協同、回饋)。這個區分是 LLM extraction 判斷準則的基礎,詳見 `extraction_guidelines.md`。

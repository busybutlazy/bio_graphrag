# Rule Card — secretion_trigger

- **rule_id**: `secretion_trigger`
- **Pattern**: P2

## 觸發語意

某生理變數的變化**觸發**某構造分泌某激素 —— 是「觸發」,不是激素造成的「結果」。
例:「當血糖濃度升高時,胰島 β 細胞會分泌胰島素。」

## 結構簽章

```
Structure ─SECRETES→ Hormone
PhysiologicalVariable ─REGULATES_SECRETION_OF→ Hormone   (properties.trigger_direction: increase|decrease)
```

## 完整性

需同時具備 `SECRETES`(誰分泌)與 `REGULATES_SECRETION_OF`(什麼觸發)兩條邊;觸發方向放在
`REGULATES_SECRETION_OF` 的 `properties.trigger_direction`。**本 pattern 沒有 RegulatoryEffect**
—— 血糖升高是觸發條件,不是胰島素造成的效果,這是正確性關鍵。

## 反向翻譯模板

> 當{variable}{升高|降低}時,{structure}會分泌{hormone}。

## 最小斷言(gold)

- `has_node_types`: `Structure`（激素/變數常是 references_existing,不強制在本案提出）
- `has_edge_types`: `SECRETES`, `REGULATES_SECRETION_OF`
- `direction`: `null`（方向在 trigger_direction,不是效果方向邊）

## 正例

```
nodes: structure:pancreatic_beta_cell (label「胰島β細胞 / pancreatic beta cell」)
edges: pancreatic_beta_cell ─SECRETES→ insulin
       blood_glucose ─REGULATES_SECRETION_OF→ insulin  { trigger_direction: "increase" }
references_existing: hormone:insulin, physiological_variable:blood_glucose
```

## 常見誤解(did_not_understand_as)

- 「胰島素造成血糖上升」(把觸發誤成效果,且方向錯)。
- 「血糖升高是胰島素作用的結果」(因果反向)。

> 註:β 細胞現行無 `CellType`,暫以 `Structure` 表達,細胞層級語意保留在 label;
> `CellType` 記於 `schema_gap_backlog.json`。

# Rule Card — antagonistic_interaction

- **rule_id**: `antagonistic_interaction`
- **Pattern**: P4

## 觸發語意

兩個激素在同一變數上作用方向相反(拮抗)。展示 **fact-node 紀律**與**跨 chunk 概念重用**:
拮抗不是激素間直接互相抑制,而是「透過兩個方向相反的既有調控效果」。
例:「胰島素與升糖素在血糖調控上具有拮抗作用。」

## 結構簽章

```
Interaction { interaction_type: antagonism } ─USES_EFFECT→ RegulatoryEffect  (×2)
Interaction ─ON_VARIABLE→ PhysiologicalVariable
```

兩個 `RegulatoryEffect` 通常是**既有**的(references_existing),由 `single_regulatory_effect`
在別的 chunk 先提出;本 pattern 只新增 Interaction 節點與引用邊,不重造效果。

## 完整性

Interaction 需至少兩條 `USES_EFFECT` 與一條 `ON_VARIABLE`;缺則 `fail_pattern`。
不新增 `AntagonisticInteraction` 專用型別 —— 用 `Interaction + interaction_type` 屬性表達
(見 `docs/expert-in-the-loop-plan.md` D4)。

## 反向翻譯模板

> {A}與{B}透過方向相反的兩個調控效果,在{variable}上呈現拮抗。

(A、B 為兩個被引用效果背後的激素,由 `HAS_EFFECT` 邊回推。)

## 最小斷言(gold)

- `has_node_types`: `Interaction`
- `has_edge_types`: `USES_EFFECT`, `ON_VARIABLE`
- `direction`: `null`

## 正例

```
new:  interaction:insulin_glucagon_blood_glucose (Interaction, interaction_type: antagonism)
edges: interaction ─USES_EFFECT→ re:insulin_decreases_blood_glucose
       interaction ─USES_EFFECT→ re:glucagon_increases_blood_glucose
       interaction ─ON_VARIABLE→ blood_glucose
references_existing: 兩個 RegulatoryEffect + physiological_variable:blood_glucose
```

## 常見誤解(did_not_understand_as)

- 「胰島素抑制升糖素」/「升糖素抑制胰島素」(把拮抗誤成激素間的直接抑制)。

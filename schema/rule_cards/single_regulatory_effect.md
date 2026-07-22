# Rule Card — single_regulatory_effect

- **rule_id**: `single_regulatory_effect`
- **Pattern**: P1

## 觸發語意

某激素造成某生理變數單向升/降的單一調控效果。
例:「胰島素會降低血糖濃度。」

## 結構簽章

```
Hormone ─HAS_EFFECT→ RegulatoryEffect ─ON_VARIABLE→ PhysiologicalVariable
RegulatoryEffect ─[INCREASES|DECREASES]→ PhysiologicalVariable
```

## 三段式 / 完整性

RegulatoryEffect 必須同時有:入邊 `HAS_EFFECT`、出邊 `ON_VARIABLE`、以及一條
`INCREASES` 或 `DECREASES` 方向邊。缺任一 → `fail_pattern`。方向由邊承載,不放節點屬性。

## 反向翻譯模板

> {hormone}會造成一個調控效果:使{variable}{上升|下降}。

## 最小斷言(gold)

- `has_node_types`: `Hormone`, `PhysiologicalVariable`, `RegulatoryEffect`
- `has_edge_types`: `HAS_EFFECT`, `ON_VARIABLE`, `INCREASES` 或 `DECREASES`
- `direction`: `increase` | `decrease`

## 正例

```
nodes: hormone:insulin / physiological_variable:blood_glucose /
       regulatory_effect:insulin_decreases_blood_glucose (RegulatoryEffect)
edges: insulin ─HAS_EFFECT→ re ; re ─ON_VARIABLE→ blood_glucose ; re ─DECREASES→ blood_glucose
```

## 常見誤解(did_not_understand_as)

- 「胰島素直接分解血糖中的葡萄糖」(把調控誤成物理分解)。
- 「血糖下降造成胰島素分泌」(把效果與觸發方向搞反 → 見 `secretion_trigger`)。

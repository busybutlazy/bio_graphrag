# Relationship Types

適用範圍:sample biology graph(激素調控主題),對應 `docs/graph_plan.md` 4.2 節。

## Relationship Type 列表

| Relationship | 意義 | 範例 |
|---|---|---|
| PART_OF | 組成關係 | Mitochondria PART_OF Cell |
| SECRETES | 分泌 | Pancreas SECRETES Insulin |
| SECRETED_BY | 分泌來源 | Insulin SECRETED_BY Pancreas |
| BINDS_TO | 激素與受器結合 | Insulin BINDS_TO Insulin receptor |
| TARGETS | 作用目標 | Insulin TARGETS Liver |
| HAS_EFFECT | 調控者具有某個調控效果 | Insulin HAS_EFFECT Insulin lowers blood glucose |
| ON_VARIABLE | 調控效果作用於某個生理變因 | Insulin lowers blood glucose ON_VARIABLE Blood glucose |
| INCREASES | 調控效果提高某個變因 | Glucagon raises blood glucose INCREASES Blood glucose |
| DECREASES | 調控效果降低某個變因 | Insulin lowers blood glucose DECREASES Blood glucose |
| REGULATES_SECRETION_OF | 生理變因調節激素分泌 | High blood glucose REGULATES_SECRETION_OF Insulin |
| PARTICIPATES_IN | 節點參與某個交互作用或回饋迴路 | Insulin PARTICIPATES_IN Blood glucose negative feedback |
| USES_EFFECT | 高階互動由哪些調控效果構成 | Antagonism USES_EFFECT Insulin lowers blood glucose |
| CATALYZES | 催化 | Amylase CATALYZES Starch breakdown |
| PREREQUISITE_OF | 先備知識 | Cell membrane PREREQUISITE_OF Osmosis |
| CAUSES | 導致 | Insulin deficiency CAUSES Hyperglycemia |
| EVIDENCED_BY | 實驗支持 | DNA as genetic material EVIDENCED_BY Hershey-Chase |
| COMMONLY_CONFUSED_WITH | 常混淆 | Mitosis COMMONLY_CONFUSED_WITH Meiosis |

## 建模原則

激素調控類的效果一律走三段式,不要用單一語意壓縮的關係:

```text
Hormone -> HAS_EFFECT -> RegulatoryEffect -> ON_VARIABLE -> PhysiologicalVariable
Interaction -> USES_EFFECT -> RegulatoryEffect
FeedbackLoop -> USES_EFFECT -> RegulatoryEffect
```

**不建議**:

```text
Insulin -> ANTAGONISTIC_TO -> Glucagon
```

因為這會遺失「在哪個生理變因上拮抗」以及「兩者各自造成什麼方向的效果」。**應該**寫成:

```text
Insulin -> HAS_EFFECT -> Insulin lowers blood glucose -> DECREASES -> Blood glucose
Glucagon -> HAS_EFFECT -> Glucagon raises blood glucose -> INCREASES -> Blood glucose
Antagonism interaction -> USES_EFFECT -> Insulin lowers blood glucose
Antagonism interaction -> USES_EFFECT -> Glucagon raises blood glucose
Antagonism interaction -> ON_VARIABLE -> Blood glucose
```

## 關係共同屬性

| 屬性 | 型別 | 說明 |
|---|---|---|
| `status` | string | `proposed` / `approved` / `rejected` / `deprecated`,與節點同一套狀態機 |

關係沒有 `merged` 狀態——merge 只發生在節點層級,節點合併時,原節點上的關係會被 curation workflow 改指向合併後的目標節點(見 `graph_schema.md` 的 curation 流程)。

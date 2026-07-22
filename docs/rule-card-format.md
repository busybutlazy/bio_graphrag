# Rule Card 格式

Rule card 把一個**萃取 pattern** 寫成人可讀、機器可對照的規格:AI 依它擬提案,工程師 gate
依它判形式,反向翻譯器依它產白話,gold 依它導最小斷言。卡片放在 `schema/rule_cards/*.md`,
檔名即 `rule_id`(如 `single_regulatory_effect.md`)。

## 必要欄位

| 欄位 | 說明 |
|---|---|
| `rule_id` | 穩定識別碼,對應 `applied_rule_ids` 與反向翻譯 pattern |
| Pattern | 對應反向翻譯的 P 編號(P1–P5) |
| 觸發語意 | 什麼樣的原文句子適用這條規則 |
| 結構簽章 | 節點型別 + 邊型別的最小組合(工程師 gate 的 `pattern_validation` 據此) |
| 三段式/完整性 | 必備的邊與方向,缺一即 `fail_pattern` |
| 反向翻譯模板 | 白話輸出模板(專家看到的句型) |
| 最小斷言 | gold 應涵蓋的 `has_node_types` / `has_edge_types` / `direction` |
| 正例 | 對齊現行 schema 的一個完整範例 |
| 反例 / 常見誤解 | 專家常見的錯誤理解(對應 `did_not_understand_as`) |

## 撰寫原則

- **對齊現行 schema 優先**:能用既有型別合理表達就對齊,只有真的表達不了才當 schema gap
  (見 `docs/expert-in-the-loop-plan.md` D1)。
- **方向由邊表達**,不是節點屬性:`INCREASES` / `DECREASES` 邊承載方向。
- **事實走三段式**:`Hormone ─HAS_EFFECT→ RegulatoryEffect ─ON_VARIABLE→ Variable`
  再加方向邊;調控效果是獨立 fact node,可被跨 chunk 重用。
- 一張卡只描述一個 pattern;跨 pattern 的組合(如拮抗引用兩個效果)在對應卡片裡說明引用關係。

現有卡片:`single_regulatory_effect`、`secretion_trigger`、`antagonistic_interaction`。
型別定義見 `schema/node_types.md` 與 `schema/relationship_types.md`。

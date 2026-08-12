# Rule Card — feedback_loop

- **rule_id**: `feedback_loop`
- **Pattern**: P6

## 觸發語意

一組調控效果構成閉環:效果最終會回頭影響觸發它自己的變因。展示**閉環紀律**——
迴路是既有效果的組合,不是新的因果宣稱。
例:「胰島素與升糖素這兩種作用相反的激素,共同將血糖維持在穩定範圍,是負回饋調節的典型例子。」

只描述單向效果、沒有描述「回頭影響」時,建 `RegulatoryEffect` 即可,不要建 `FeedbackLoop`。

## 結構簽章

```
FeedbackLoop { feedback_type: negative|positive, regulated_variable: <變因名> }
  ─USES_EFFECT→ RegulatoryEffect  (×1 以上)
```

被引用的 `RegulatoryEffect` 通常是**既有**的(references_existing),由 `single_regulatory_effect`
在別的 chunk 先提出;本 pattern 只新增 FeedbackLoop 節點與引用邊,不重造效果。

## 完整性

需至少一條 `USES_EFFECT`,且節點屬性須有 `feedback_type`(`negative`/`positive`)
與 `regulated_variable`;缺任一 → `fail_pattern`。

兩點與其他卡片不同,是**刻意**的,不是遺漏:

1. **只要求一條 `USES_EFFECT`**(拮抗要求兩條)。閉環不必然由兩個效果構成:現行已核准的
   四個迴路中有三個(血鈣、血漿滲透壓、子宮收縮)只引用單一效果。要求兩條會把已策展
   的知識判成不合格。
2. **被調控變因寫在節點屬性 `regulated_variable`,不是 `ON_VARIABLE` 邊**(拮抗用邊)。
   這是沿用既有已核准迴路的形狀,避免為了格式統一而回頭改動人工策展過的資料。
   `docs/rule-card-format.md` 的「關係由邊表達」原則在此開了一個有紀錄的例外;
   若日後決定對齊 Interaction,需一併更新 `data/sample` 並重跑 `make export-seed`。

## 反向翻譯模板

> {A}與{B}的調控效果構成{variable}的{負|正}回饋迴路。

(A、B 為被引用效果背後的激素,由 `HAS_EFFECT` 邊回推;只引用一個效果時只列一個。)

## 最小斷言(gold)

- `has_node_types`: `FeedbackLoop`
- `has_edge_types`: `USES_EFFECT`
- `direction`: `null`（方向在被引用的效果上,不在迴路本身）

## 正例

```
new:  feedback:blood_glucose_negative_feedback (FeedbackLoop,
        feedback_type: negative, regulated_variable: blood_glucose)
edges: feedback:blood_glucose_negative_feedback ─USES_EFFECT→ regulatory_effect:insulin_decreases_blood_glucose
       feedback:blood_glucose_negative_feedback ─USES_EFFECT→ regulatory_effect:glucagon_increases_blood_glucose
references_existing: 兩個 RegulatoryEffect
```

## 常見誤解(did_not_understand_as)

- 「負回饋就是激素互相抑制」(把迴路誤成激素之間的直接抑制,與 `antagonistic_interaction` 同源誤解)。
- 「血糖穩定就代表有回饋迴路」(把結果當成結構;原文須描述回頭影響的閉環)。
- 把 `positive` 讀成「有益」——正回饋指的是放大原刺激,與好壞無關。

# Demo Cases — 血糖調控

> 對應 `data/sample/expert_demo/cases.json`(7 案例);計畫見 `docs/expert-in-the-loop-plan.md`。
> 全部對齊現行 schema(決策 D1=A);只有 Case 5 是真的 schema gap。Case 6/7 是**退回**案例
> (`changes/expert-gate-integrity`),展示兩道 gate 都會擋。
> 每個節點/邊已通過 `extraction_output_schema` 驗證(型別、id 慣例、必填、無多餘欄位、端點可解析)。

「系統理解」由 deterministic renderer(`back_translation.py`)當場產生;「工程師 gate」由
`engineer_gate.py` 當場計算(已實作)。以下每案標註的是其**基準結果**,`tests/gold` 與
`tests/unit/test_engineer_gate.py` 逐條回歸。

---

## Case 1 — 單一調控效果

**原文**:胰島素會降低血糖濃度。

**Graph**
```
hormone:insulin ─HAS_EFFECT→ regulatory_effect:insulin_decreases_blood_glucose
regulatory_effect:insulin_decreases_blood_glucose ─ON_VARIABLE→ physiological_variable:blood_glucose
regulatory_effect:insulin_decreases_blood_glucose ─DECREASES→ physiological_variable:blood_glucose
```

**系統理解(P1)**:胰島素 會造成一個調控效果:使 血糖 下降。

**系統沒有理解成**:胰島素直接分解血糖中的葡萄糖;血糖下降造成胰島素分泌。

**工程師 gate**:pass(全綠)　**專家**:approved

---

## Case 2 — 多步驟(mechanism vs result)

**原文**:升糖素會促進肝醣分解,使血糖上升。

**Graph**(新增:Glucagon、其 RegulatoryEffect、Glycogenolysis;blood_glucose 引用自 Case 1)
```
hormone:glucagon ─HAS_EFFECT→ regulatory_effect:glucagon_increases_blood_glucose
regulatory_effect:glucagon_increases_blood_glucose ─ON_VARIABLE→ physiological_variable:blood_glucose  (既有)
regulatory_effect:glucagon_increases_blood_glucose ─INCREASES→ physiological_variable:blood_glucose  (既有)
hormone:glucagon ─CAUSES→ process:glycogenolysis          ← mechanism(決策 D5)
```

**系統理解(P3)**:升糖素 會促成肝醣分解,並造成調控效果:使 血糖 上升。

**系統沒有理解成**:升糖素直接把血糖變高,與肝醣分解無關;升糖素只是與血糖上升相關,沒有方向。

**工程師 gate**:pass　**專家**:approved
**建模備註**:現行 schema 無「效果透過 process 實現」的專用邊,mechanism 暫用 `CAUSES` 掛在 Hormone 上;事實仍走三段式。未來可提軟性 `ACTS_VIA` backlog,非 MVP。

---

## Case 3 — 分泌觸發

**原文**:當血糖濃度升高時,胰島 β 細胞會分泌胰島素。

**Graph**(新增:β細胞;insulin、blood_glucose 引用自 Case 1)
```
structure:pancreatic_beta_cell ─SECRETES→ hormone:insulin(既有)
physiological_variable:blood_glucose(既有) ─REGULATES_SECRETION_OF→ hormone:insulin(既有)
        (edge properties: trigger_direction = increase)
```
β 細胞用 `Structure`,label 保留「胰島β細胞 / pancreatic beta cell」(決策 D3);CellType 進 backlog。

**系統理解(P2)**:當 血糖 濃度升高時,胰島β細胞 會分泌 胰島素。

**系統沒有理解成**:胰島素造成血糖上升;血糖升高是胰島素作用的結果。

**工程師 gate**:pass　**專家**:approved
**正確性關鍵**:血糖高是**觸發**(REGULATES_SECRETION_OF),不是胰島素造成的**結果**,故此案例**無** RegulatoryEffect。

---

## Case 4 — 拮抗

**原文**:胰島素與升糖素在血糖調控上具有拮抗作用。

**Graph**(新增只有 Interaction 及其 3 條邊;兩個 RegulatoryEffect 引用自 Case 1、Case 2)
```
interaction:insulin_glucagon_blood_glucose (interaction_type=antagonism, scope=blood_glucose_regulation)
       ─USES_EFFECT→ regulatory_effect:insulin_decreases_blood_glucose   (既有)
       ─USES_EFFECT→ regulatory_effect:glucagon_increases_blood_glucose  (既有)
       ─ON_VARIABLE→ physiological_variable:blood_glucose
```

**系統理解(P4)**:胰島素 與 升糖素 透過方向相反的兩個調控效果,在 血糖 上呈現拮抗。

**系統沒有理解成**:胰島素抑制升糖素;升糖素抑制胰島素。

**工程師 gate**:pass　**專家**:approved
**展示點**:拮抗是「在血糖上、透過兩個反向 effect」,非激素間直接互抑;Interaction 依賴已存在的兩個 fact node(既有概念重用),符合 guideline「Interaction 不能無中生有」。

---

## Case 5 — permissive effect(唯一硬 schema gap)

**原文**:甲狀腺素會增強腎上腺素對代謝作用的效果。

**Graph**(可 schema-valid 的部分:3 個節點,無法建出核心關係的邊)
```
hormone:thyroxine
hormone:adrenaline
physiological_variable:metabolic_rate
proposed_edges: (空 — 「甲狀腺素改變腎上腺素對代謝的作用強度」無對應 edge)
possible_schema_gap: true
```

**系統理解(P5)**:系統目前無法用既有的知識結構完整表達此現象。

**系統沒有理解成**:甲狀腺素單獨提高代謝率;腎上腺素單獨提高代謝率;兩者之間是單純因果。

**工程師 gate**:needs_schema_extension(型別/ID valid,但核心宣稱無 pattern,back_translation 不可用)
**專家**:schema_gap → 白話「A 不是直接影響 C,而是改變 B 對 C 的作用強度」→ `schema_gap_type: permissive_effect` → 進 backlog

---

## Case 6 — 形式退回(engineer gate 攔下,不進專家審查)

> `changes/expert-gate-integrity` 新增;展示**工程師 gate 真的會擋**。

**原文**:腎上腺素會影響血糖。

**Graph**(方向未定,三段式無法完成)
```
hormone:adrenaline ─HAS_EFFECT→ regulatory_effect:adrenaline_affects_blood_glucose
(缺 ON_VARIABLE 與 INCREASES/DECREASES 方向邊 — 原文只說「影響」,方向不明)
```

**工程師 gate**:`fail_pattern`(schema/型別/id 皆合法,但 RegulatoryEffect 三段式不完整)
**專家**:`not_reviewed` — 形式問題依流程**退回修 proposal,不勞煩專家**;前端專家分頁顯示「已於工程師 gate 退回」,**不**顯示會誤導的 gap 白話。

---

## Case 7 — 意義退回(form-valid 但生物學錯誤;marquee)

> `changes/expert-gate-integrity` 新增;展示**形式 ✓ ≠ 意義 ✓**,兩道 gate 互相獨立。

**原文**:胰島素會降低血糖濃度。

**Graph**(三段式完整、schema 合法,但方向被抽反)
```
hormone:insulin ─HAS_EFFECT→ regulatory_effect:insulin_increases_blood_glucose
regulatory_effect:insulin_increases_blood_glucose ─ON_VARIABLE→ physiological_variable:blood_glucose
regulatory_effect:insulin_increases_blood_glucose ─INCREASES→ physiological_variable:blood_glucose  ← 錯:胰島素應降血糖
```

**系統理解(P1)**:胰島素 會造成一個調控效果:使 血糖 上升。(← 與原文相反)

**工程師 gate**:`pass`(形式完全合法)
**專家**:`rejected` — 領域專家讀「原文 vs 系統理解」即見方向相反,退回。這是**只有意義 gate 才攔得下**、形式檢查看不出的錯誤。

---

## 案例一覽

| Case | 主題 | 規則 | 工程師 gate | 專家 | schema gap |
|---|---|---|---|---|---|
| 1 | 單一調控效果 | single_regulatory_effect | pass | approved | — |
| 2 | mechanism vs result | regulatory_effect_with_mechanism | pass | approved | — |
| 3 | 分泌觸發 | secretion_trigger | pass | approved | — |
| 4 | 拮抗 | antagonistic_interaction | pass | approved | — |
| 5 | permissive effect | (none) | needs_schema_extension | schema_gap | permissive_effect |
| 6 | 形式退回 | (incomplete) | **fail_pattern** | not_reviewed | — |
| 7 | 意義退回(方向抽反) | single_regulatory_effect | pass | **rejected** | — |

> 專家決定經 `POST /admin/expert-demo/reviews` 寫成 `graph_change_logs` 的 append-only 稽核列
> (`action='expert_review'`),與 curation 用同一條稽核軌。

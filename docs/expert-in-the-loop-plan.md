# Expert-in-the-loop Graph Extraction Governance — 計畫與 Roadmap

> 狀態:**已實作**(Phase A–C 完成並合併;見 commit `828ebf4` 等)。後續整合工作
>   (G2 專家審查稽核持久化、G5 兩個 rejection 案例、文件校正)見
>   `changes/expert-gate-integrity/`。
> 建立日期:2026-07-09　|　最後更新:2026-07-23
> 範圍:MVP 為固定資料的展示型 workflow demo,不接真 pipeline、不改 schema 型別

本文件記錄「萃取規則 governance」這一階段的**設計決策、討論脈絡與實作 roadmap**。
實作階段才會產出的操作文件(workflow / rule-card-format / schema-gap-policy /
demo-cases)另立檔案,本文件是它們的上游計畫與決策紀錄。

---

## 一、目標與核心亮點

本階段不是單純讓 LLM 從文本抽 entity/relation,而是模擬一套正式知識工程流程:

1. AI 依文本與現有 schema 擬出 graph proposal。
2. **工程師 gate** 檢查形式(schema / pattern / 可測試性)。
3. 系統把 graph **反向翻譯**成專家能讀的白話 + 概念圖。
4. **專家 gate** 只審生物語意,不看 JSON。
5. 專家意見被結構化保存;無法表達的現象進 **schema gap backlog**。
6. 通過審查的案例固化成 **gold examples** 與 **regression tests**。

一句話定位:

> 讓非工程背景的領域專家,也能參與 GraphRAG 萃取規則審查,
> 並把專家知識轉換成可測試、可追蹤、可演進的工程資產。

---

## 二、核心設計原則(討論結論)

### 1. 工程師 gate 與專家 gate 必須分離 —— 「形式 vs 意義」

- **工程師管形式(form)**:是否過 `extraction_output_schema`、型別是否存在、三段式是否成立、
  能否被 deterministic renderer 反向翻譯、能否轉成 gold test、是否造成重複/污染。
- **專家管意義(meaning)**:系統理解是否符合原文、有無過度推論、有無漏掉重要概念、
  是否把弱關聯誤判成因果、是否有 schema 表達不了的現象、用詞是否合教材慣例。

技術背景的人同時扮兩角,最常見的失敗是「用 JSON valid 代替生物學正確」。
因此工具用**檔案/tab 邊界**強制隔離兩種審查面,而不是靠註解或自律。

### 2. 專家不看 JSON

專家畫面只呈現:原文、系統理解(白話)、概念圖、系統沒理解成什麼、審查選項、備註。
不呈現:raw JSON、schema code、node/edge id、內部 gap code、prompt 輸出。

### 3. 反向翻譯優先用 deterministic renderer

「系統理解」不讓 LLM 自由生成,否則專家看到的可能不是 graph 真正表達的內容。
流程:`graph proposal → deterministic renderer 套 pattern 模板 → 專家畫面`。
(LLM 潤飾層 MVP 不做 — YAGNI。)

### 4. 專家用白話標記 schema gap

專家不需要知道內部 gap code。UI 顯示白話選項,系統內部再映射成 `schema_gap_type`。

---

## 三、已定案決策(Decision Log)

| # | 決策 | 選擇 | 理由 |
|---|---|---|---|
| D1 | Case 3/4 用到現行 schema 沒有的型別怎麼辦 | **A:對齊現行 schema** | MVP 主軸是展示 governance,不是現在重構 schema;能合理表達就先對齊,只有真的表達不了的才當 gap |
| D2 | 固定 demo data 怎麼餵前端 | **a:後端 read-only endpoint 讀 `cases.json`** | 最貼合現有 `api.get` 慣例、成本極低、一致性最好 |
| D3 | Case 3 的「胰島 β 細胞」 | 用 **Structure**,label 保留「胰島β細胞 / pancreatic beta cell」 | 現行無 CellType;label 保留細胞層級語意,CellType 進 backlog |
| D4 | Case 4 的拮抗 | **Interaction node + `interaction_type: antagonism`**,經兩個反向 RegulatoryEffect,`USES_EFFECT` 引用 + `ON_VARIABLE` 到 blood glucose | 不新增 AntagonisticInteraction 型別;符合現有 fact-node 紀律 |
| D5 | Case 2 的 mechanism(肝醣分解)怎麼掛 | 用 **`CAUSES`**(Hormone→Process),事實仍走三段式 | 現行無「效果透過 process 實現」的專用邊;`CAUSES` 語意成立且 schema-valid;非硬 gap |

**明確排除於 MVP schema 之外(只記 backlog,不實作)**:
`CellType`、`Stimulus`、`STIMULATES`、`AntagonisticInteraction`、`ON_PROCESS`。

---

## 四、五個 Demo Cases 規格(對齊現行 schema)

節點欄位:`id/type/label/description/source_chunk_id`;邊:`id/type/source/target/source_chunk_id`。
方向由 `INCREASES/DECREASES` 邊表達(非節點屬性)。
三段式:`Hormone ─HAS_EFFECT→ RegulatoryEffect ─ON_VARIABLE→ Variable` 再加 `─INCREASES|DECREASES→ Variable`。

### Case 1 — 單一調控效果(全綠)
原文:「胰島素會降低血糖濃度。」
```
nodes: hormone:insulin / physiological_variable:blood_glucose /
       regulatory_effect:insulin_decreases_blood_glucose (RegulatoryEffect)
edges: insulin ─HAS_EFFECT→ re:insulin_decreases_blood_glucose
       re:insulin_decreases_blood_glucose ─ON_VARIABLE→ blood_glucose
       re:insulin_decreases_blood_glucose ─DECREASES→ blood_glucose
rule: single_regulatory_effect      expert: approved
```

### Case 2 — 多步驟(mechanism vs result,全綠)
原文:「升糖素會促進肝醣分解,使血糖上升。」
```
nodes: hormone:glucagon / process:glycogenolysis (Process) /
       physiological_variable:blood_glucose /
       regulatory_effect:glucagon_increases_blood_glucose (RegulatoryEffect)
edges: glucagon ─HAS_EFFECT→ re:glucagon_increases_blood_glucose
       re:glucagon_increases_blood_glucose ─ON_VARIABLE→ blood_glucose
       re:glucagon_increases_blood_glucose ─INCREASES→ blood_glucose
       glucagon ─CAUSES→ process:glycogenolysis        ← mechanism 節點(見 D5)
rule: regulatory_effect_with_mechanism   expert: approved
```

### Case 3 — 分泌觸發(全綠)
原文:「當血糖濃度升高時,胰島 β 細胞會分泌胰島素。」
```
nodes: physiological_variable:blood_glucose /
       structure:pancreatic_beta_cell (Structure, label「胰島β細胞 / pancreatic beta cell」) /
       hormone:insulin
edges: structure:pancreatic_beta_cell ─SECRETES→ insulin
       blood_glucose ─REGULATES_SECRETION_OF→ insulin
              (edge properties: { trigger_direction: "increase" })
rule: secretion_trigger   expert: approved
```
正確性關鍵:血糖高是**觸發**(`REGULATES_SECRETION_OF`),不是胰島素造成的**結果**,故無 RegulatoryEffect。

### Case 4 — 拮抗(全綠;展示 fact-node 紀律 + 跨 chunk 概念重用)
原文:「胰島素與升糖素在血糖調控上具有拮抗作用。」
```
引用既有(Case 1、Case 2 已提出的 effect id):
       re:insulin_decreases_blood_glucose / re:glucagon_increases_blood_glucose
本 case 新增:
nodes: interaction:insulin_glucagon_blood_glucose
              (Interaction, interaction_type: antagonism, scope: blood_glucose_regulation)
edges: interaction ─USES_EFFECT→ re:insulin_decreases_blood_glucose
       interaction ─USES_EFFECT→ re:glucagon_increases_blood_glucose
       interaction ─ON_VARIABLE→ blood_glucose
rule: antagonistic_interaction   expert: approved
did_not_understand_as: 「胰島素抑制升糖素」/「升糖素抑制胰島素」
```

### Case 5 — permissive effect(唯一硬 schema gap)
原文:「甲狀腺素會增強腎上腺素對代謝作用的效果。」
```
AI 提案 schema-valid 部分:hormone:thyroxine / hormone:adrenaline /
       physiological_variable:metabolic_rate,自標 possible_schema_gap: true
無法表達的核心關係:「甲狀腺素改變腎上腺素對代謝的作用強度」→ 無對應 pattern
engineer_gate: 型別/ID valid,但 back_translation_available = fail → needs_schema_extension
expert: schema_gap → 白話「A 不是直接影響 C,而是改變 B 對 C 的作用強度」
        → schema_gap_type: permissive_effect → 進 backlog
```

---

## 五、七項元件規格

### 1. `cases.json` 結構(`data/sample/expert_demo/cases.json`)
每筆:`id / domain / source_text / proposal{proposed_nodes, proposed_edges,
references_existing, confidence, applied_rule_ids, uncertain_points,
possible_over_inference, possible_schema_gap} / did_not_understand_as[] /
expert_review{status, notes, schema_gap_type, reviewed_by, reviewed_at} /
gold{promote, gold_id}`。

- **不存** `system_understanding`(由 renderer 當場算,證明 renderer 是真的)。
- **不存** engineer gate 結果(由 `engineer_gate` module 當場算,證明 gate 是真的)。
- `expert_review` 是 demo 預設「標準答案」,前端可覆寫並存 sessionStorage。

### 2. `back_translation` renderer(`backend/app/graph/back_translation.py`)
純函式,以結構簽章 pattern-match,無模板引擎、不呼叫 LLM:

| Pattern | 結構簽章 | 輸出模板 |
|---|---|---|
| P1 single_regulatory_effect | `Hormone ─HAS_EFFECT→ RE ─ON_VARIABLE/[INC\|DEC]→ Var` | 「{regulator} 會造成一個調控效果:使 {variable} {direction_zh}。」 |
| P2 secretion_trigger | `Var ─REGULATES_SECRETION_OF→ Hormone` + `Structure ─SECRETES→ Hormone` | 「當 {variable}{trigger_zh}時,{structure} 會分泌 {hormone}。」 |
| P3 regulatory_effect_with_mechanism | P1 + `Hormone ─CAUSES→ Process` | 「{hormone} 會促成{process},並造成調控效果:使 {variable} {direction_zh}。」 |
| P4 antagonistic_interaction | `Interaction{antagonism} ─USES_EFFECT→ RE×2, ─ON_VARIABLE→ Var` | 「{A} 與 {B} 透過方向相反的兩個調控效果,在 {variable} 上呈現拮抗。」 |
| P5 schema_gap | 核心宣稱無任何 pattern 命中 | 「系統目前無法用既有的知識結構完整表達此現象。」 |

`direction_zh`: increase→上升 / decrease→下降。`trigger_zh`: 由 edge `properties.trigger_direction` 映射。

### 3. `engineer_gate`(`backend/app/graph/engineer_gate.py`,複用既有驗證)

| 檢查 | 實作 | 失敗碼 |
|---|---|---|
| schema_validation | `validate_extraction.validate_extraction_output()` | fail_schema |
| node_type_validation | `∈ VALID_NODE_TYPES` | fail_schema |
| edge_type_validation | `∈ VALID_RELATIONSHIP_TYPES` | fail_schema |
| id_convention_validation | `^[a-z_]+:[a-z0-9_]+$` | fail_schema |
| pattern_validation | 三段式/Interaction 完整性 | fail_pattern |
| back_translation_available | renderer 能產非 gap 句子 | needs_schema_extension |
| testability | 已知 pattern → 可導 min assertions | fail_testability |
| duplication_risk | id 撞既有 / 有 possible_duplicate_of | (標記不擋) |

`result ∈ {pass, fail_schema, fail_pattern, fail_testability, needs_schema_extension}`。
只有 Case 5 → `needs_schema_extension`。gate **不碰生物語意**。

### 4. Expert Review Demo UI
新 view `{ id:'expert', label:'審閱' }`,左側 5 案例、右側 3 sub-tab:
- **Tab1 AI Proposal**(工程師/面試官):原文、summary、nodes、edges、confidence、uncertain。可顯示 JSON/id。
- **Tab2 Engineer Gate**:逐項 pass/fail 燈號(當場計算),fail 顯示原因。
- **Tab3 Expert Review**(專家,強制隔離):原文、系統理解(當場 render)、概念圖(複用 `renderGraph`)、
  系統沒理解成、審查 radio、備註。**不顯示** JSON/id/schema code/gap code/prompt。
  選「無法表達」→ 展開白話 gap radio。選擇存 sessionStorage。
資料源:`GET /admin/expert-demo/cases`(read-only,admin key,讀 `cases.json`)。

### 5. Gold minimum assertions(`data/sample/expert_demo/gold/*.json`)
每筆存結構性最小斷言(非完整 equality):`expected_understanding`(renderer 回歸基準)+
`min_assertions{has_node_types, has_edge_types, direction}`。
`backend/tests/gold/test_gold_examples.py` 逐條斷言;MVP 先打固定 proposal,未來換真 pipeline。

### 6. Schema gap backlog
白話 ⇄ code 映射(進 `docs/schema-gap-policy.md`):

| 專家看到(白話) | `schema_gap_type` |
|---|---|
| A 不是直接影響 C,而是改變 B 對 C 的作用強度 | `permissive_effect` |
| A 和 B 之間不是因果,而是拮抗/協同 | `antagonistic_or_synergistic_interaction` |
| 這是一個多步驟調控路徑,不是單一效果 | `pathway_or_cascade` |
| 這是一個條件式效果,需要特定前提才成立 | `conditional_effect` |
| 這是一個閾值效果 | `threshold_effect` |
| 其他 | `unknown` |

Backlog 資料(`data/sample/expert_demo/schema_gap_backlog.json`):
`gap_id / raised_by_case / schema_gap_type / expert_facing_reason / example_text /
status(backlog|proposed|accepted|rejected) / proposed_schema_change / raised_at`。
D6 排除的型別(CellType/Stimulus/STIMULATES/AntagonisticInteraction/ON_PROCESS)一併記為 backlog。

---

## 六、複用資產(不重造)

| 需求 | 直接複用 | 位置 |
|---|---|---|
| 決策溯源/audit | `graph_change_logs`(actor/reason/before/after) | `schema.sql`、`curation/service._log_change` |
| proposed→review 狀態 | `curation_items` | `schema.sql` |
| 工程師 gate 驗證 | `validate_extraction_output` + 型別白名單 | `validate_extraction.py`、`normalize_concepts.py` |
| 概念圖渲染 | `renderGraph` SVG | `frontend/app.js` |
| Tab/卡片/pill/DOM helper | `renderIngest`/`renderCuration`/`E()`/`svgEl()` | `frontend/app.js` |
| 視覺基底 | design tokens + 06/07 稿 | `design_handoff_honzo/` |

---

## 七、MVP 邊界

**要做**:固定資料 demo、rule card 文件格式、deterministic renderer、expert review UI、
engineer gate 結果展示、gold 結構、最小 regression test、schema gap backlog。

**不做**:多使用者/專家帳號/權限、真 pipeline 接入、prompt auto-optimization、
schema migration UI、production-grade audit、LLM 潤飾層、任何 `schema/` 型別變更。

---

## 八、Roadmap

分三階段,每步可獨立驗證。標註 `[ ]` 供追蹤。

### Phase A — 地基:案例定稿(先跑一遍「專家 gate」)
- [x] A1 `docs/demo-cases-blood-glucose.md`:5 案例 graph 定稿
- [x] A2 `data/sample/expert_demo/cases.json`:對應資料
- [x] A3 **戴專家帽驗收**:5 案例生物學無誤(尤其 Case 3 觸發方向、Case 4 拮抗語意、Case 5 gap 判定)

### Phase B — 引擎:renderer + gate + gold(可純後端驗證)
- [x] B1 `backend/app/graph/back_translation.py` + `tests/unit/test_back_translation.py`(P1–P5)
- [x] B2 `backend/app/graph/engineer_gate.py` + `tests/unit/test_engineer_gate.py`(複用既有驗證;Case 5 → needs_schema_extension)
- [x] B3 `data/sample/expert_demo/gold/*.json` + `tests/gold/test_gold_examples.py`(min assertions)
- [x] B4 `data/sample/expert_demo/schema_gap_backlog.json` + `docs/schema-gap-policy.md`

### Phase C — 呈現:端點 + UI + 文件收尾
- [x] C1 `backend/app/api/routes_expert_demo.py`(`GET /admin/expert-demo/cases`)+ 掛進 `main.py`
- [x] C2 前端 `renderExpertDemo` 三 tab(複用 renderGraph;Expert tab 強制隔離)+ styles
- [x] C3 `docs/expert-in-the-loop-workflow.md`、`docs/rule-card-format.md`、`schema/rule_cards/*.md`(3 張)
- [x] C4 `extraction_guidelines.md` 頂部指向 rule_cards;`README.md`/docs 索引補一段

### 驗收敘事(完成後應能展示)
1. AI 提出 graph proposal → 2. 工程師 gate 檢查形式 → 3. 反向翻譯成白話 →
4. 專家不看 JSON 也能審生物語意 → 5. 指出無法表達時記 schema gap →
6. 通過的案例固化成 gold → 7. gold 成為改 prompt/schema/pipeline 時的 regression test。

---

## 九、待辦 / 開放項

- Phase A3 專家驗收後,若任一案例的 graph 需調整,回頭改 A1/A2 再往下。
- 未來若要把 demo 接真 pipeline:gold test 從「打固定 proposal」切成「打真實抽取輸出」。
- `ACTS_VIA`(Case 2 mechanism 的精準邊)列為軟性 backlog,非 MVP。

### 更新(2026-07-23,`changes/expert-gate-integrity`)

- **G5**:新增 Case 6(形式退回 `fail_pattern`)與 Case 7(form-valid 但方向抽反 → 專家
  `rejected`),讓 demo 明確展示兩道 gate 都會擋。前端專家分頁對 `fail_*` 案例不再顯示會誤導的
  P5 gap 白話(review finding M1)。
- **G2**:§五.4 原設計為「唯讀、不寫任何 store」;現**刻意調整**為唯讀讀取 +
  `POST /admin/expert-demo/reviews` 附加式稽核寫入(`graph_change_logs`,`action='expert_review'`,
  `actor='demo-viewer'`),讓專家決定成為可追蹤資產。作者權威審查另行 seed;不碰 approved 圖。
- 仍延後:G1(於 `relationship_types.md` 補 `trigger_direction`,待接真 pipeline)、G3/G4/G6
  (實作面小清理)。

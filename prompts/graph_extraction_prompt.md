# Graph Extraction Prompt

Ingestion pipeline 的 extraction step 呼叫 LLM 時使用的 prompt 模板。對應 `schema/extraction_guidelines.md`(判斷準則)與 `schema/extraction_output_schema.json`(輸出格式)。

這是**通用 base 模板**(公開),適用所有教材。若某文件在來源資料帶了 `extraction_profile` 欄位,萃取時會把 `prompts/profiles/<name>.profile.md` 的章節特化補充疊在下面的 System Prompt 之後——用來針對不同章節指定「該重點抽出哪些 entity / relation」。這些精雕 profile 是本地 IP、不進 git(見 `prompts/profiles/README.md`);缺檔時自動退回通用行為。組裝邏輯在 `ingestion/pipeline/build_extraction_prompt.py`。

## System Prompt

```text
你是一個高中生物知識圖譜的 extraction agent。你的任務是從一段教材文字中,
抽取候選節點(node)與候選關係(edge),供人工審核後才會進入正式知識圖譜。

規則:
1. 只能使用以下 node type:Concept, System, Process, Structure, Molecule,
   Hormone, Receptor, PhysiologicalVariable, RegulatoryEffect, Interaction,
   FeedbackLoop, Enzyme, Disease, Experiment, Misconception。
2. 只能使用以下 relationship type:PART_OF, SECRETES, SECRETED_BY, BINDS_TO,
   TARGETS, HAS_EFFECT, ON_VARIABLE, INCREASES, DECREASES,
   REGULATES_SECRETION_OF, PARTICIPATES_IN, USES_EFFECT, CATALYZES,
   PREREQUISITE_OF, CAUSES, EVIDENCED_BY, COMMONLY_CONFUSED_WITH。
3. 何時建立 RegulatoryEffect / 分泌觸發 / Interaction 見下方規則 7、8、9,
   不要自行放寬。FeedbackLoop 只在文本描述「某效果會回頭影響觸發它自己的變因」
   的閉環時才建立;只有單向效果就建 RegulatoryEffect 即可。
4. 每個節點與關係都必須帶 source_chunk_id,對應到輸入文字的 chunk id。
5. 不確定的內容不要生成,寧缺勿濫。
6. 輸出必須是單一 JSON 物件,不要輸出 JSON 以外的文字、不要加註解、
   不要用 markdown code fence 包裹。形狀固定如下,**每個** node 與 edge 都必須
   帶齊全部欄位(少一個欄位,整段抽取都會被丟棄):

   {"nodes": [
      {"id": "hormone:insulin", "type": "Hormone", "label": "胰島素 / insulin",
       "description": "一到兩句說明", "source_chunk_id": "填入 user prompt 給的 chunk_id"},
      {"id": "interaction:insulin_glucagon_blood_glucose", "type": "Interaction",
       "label": "胰島素與升糖素的拮抗", "description": "一到兩句說明",
       "properties": {"interaction_type": "antagonism"},
       "source_chunk_id": "填入 user prompt 給的 chunk_id"}
    ],
    "edges": [
      {"id": "e1", "type": "HAS_EFFECT",
       "source": "hormone:insulin", "target": "regulatory_effect:insulin_decreases_blood_glucose",
       "source_chunk_id": "填入 user prompt 給的 chunk_id"}
    ]}

   關係型別放在 edge 的 "type" 欄位(不是 "relationship")。edge 的 "id" 只要在
   本次輸出內不重複即可,例如 e1、e2。上面每個 "填入…" 都是佔位說明,實際輸出
   必須換成真值,不可原樣照抄。除上列欄位外,node 可選 "properties"、
   "possible_duplicate_of",edge 可選 "properties",不要自行新增其他欄位。
7. RegulatoryEffect 只在文本明確描述「某個調控者對某個生理變因造成什麼方向的
   效果」時建立;文本只說某構造分泌某激素、或某變因觸發分泌,那是規則 8 的
   分泌觸發,**不要**建 RegulatoryEffect。

   要建的時候,關係有固定方向,不可自行調換。每一個 RegulatoryEffect 都必須配
   **恰好三條**邊,缺一條就會被退回,不可壓縮成兩條:

     (1) Hormone ─HAS_EFFECT→ RegulatoryEffect
     (2) RegulatoryEffect ─ON_VARIABLE→ PhysiologicalVariable
     (3) RegulatoryEffect ─INCREASES 或 DECREASES→ PhysiologicalVariable

   注意 (2) 與 (3) 的起點和終點完全相同,只有 type 不同——這**不是**重複,
   兩條都要輸出。(2) 說明「這個效果作用在哪個變因」,(3) 說明「往哪個方向」。
   方向只寫在節點 id 或 label 裡不算數,一定要有 (3) 這條邊。

   正例(「胰島素會降低血糖濃度」,注意 edges 有三條):
     nodes: hormone:insulin, regulatory_effect:insulin_decreases_blood_glucose,
            physiological_variable:blood_glucose
     edges: hormone:insulin ─HAS_EFFECT→ regulatory_effect:insulin_decreases_blood_glucose
            regulatory_effect:insulin_decreases_blood_glucose ─ON_VARIABLE→ physiological_variable:blood_glucose
            regulatory_effect:insulin_decreases_blood_glucose ─DECREASES→ physiological_variable:blood_glucose

   常見錯誤,不要這樣寫:
     ✗ RegulatoryEffect ─HAS_EFFECT→ PhysiologicalVariable  (該位置用 ON_VARIABLE)
     ✗ Hormone ─DECREASES→ PhysiologicalVariable            (跳過 RegulatoryEffect)
     ✗ 只建立 RegulatoryEffect 而不建立造成它的 Hormone 節點
     ✗ 只出 HAS_EFFECT 與 ON_VARIABLE 兩條,把方向留在 id 字串裡(缺第 (3) 條)

8. 分泌觸發是**另一種**結構,沒有 RegulatoryEffect。文本描述「某變因變化時,
   某構造分泌某激素」時,只出這兩條邊:

   Structure ─SECRETES→ Hormone
   PhysiologicalVariable ─REGULATES_SECRETION_OF→ Hormone
     (properties: {"trigger_direction": "increase" 或 "decrease"})

   正例(「當血糖濃度上升時,胰島 β 細胞會分泌胰島素」):
     edges: structure:pancreatic_beta_cell ─SECRETES→ hormone:insulin
            physiological_variable:blood_glucose ─REGULATES_SECRETION_OF→ hormone:insulin
              {"trigger_direction": "increase"}

   常見錯誤,不要這樣寫:
     ✗ 把「血糖升高」寫成胰島素造成的效果(那是觸發條件,因果剛好相反)
     ✗ 為分泌觸發硬造一個 RegulatoryEffect 三段式

9. Interaction 必須引用**至少兩個**既有的 RegulatoryEffect,並帶 interaction_type:
   Interaction ─USES_EFFECT→ RegulatoryEffect (×2 以上)
   Interaction ─ON_VARIABLE→ PhysiologicalVariable
   節點 properties 必須有 {"interaction_type": "antagonism"} (方向相反)
   或 {"interaction_type": "synergism"} (方向相同、共同增強);缺這個屬性,
   審閱者看不到這是拮抗還是協同。
   還沒有兩個對應的 RegulatoryEffect 之前,不要建立 Interaction。

10. 節點 id 一律 <type_prefix>:<snake_case_name>,例如 hormone:insulin。
```

## User Prompt 模板

```text
chunk_id: {chunk_id}
既有相關概念(避免重複建立,可用 possible_duplicate_of 標示疑似重複):
{existing_concepts}

教材原文:
"""
{chunk_text}
"""

請依照 system prompt 的規則,輸出這段文字中可抽取的候選節點與候選關係。

輸出前逐條檢查:每個 node 與**每一條** edge 都要有 id、type、source_chunk_id
(edge 另需 source 與 target);關係型別寫在 edge 的 type 欄位,不可寫成 relationship。
任何一條邊少欄位,整段抽取都會被丟棄。
```

## 佔位符說明

| 佔位符 | 來源 |
|---|---|
| `{chunk_id}` | ingestion pipeline 產生的 chunk id,寫入每個候選節點/關係的 `source_chunk_id` |
| `{existing_concepts}` | 從 Neo4j 查詢與本 chunk `concept_ids` 相關的既有 `approved`/`proposed` 節點清單(id + label) |
| `{chunk_text}` | 該 chunk 的原文內容 |

> 章節特化:document 來源的 `extraction_profile` 欄位(可省略)指定要疊加的 profile 名,對應 `prompts/profiles/<name>.profile.md`。欄位為空或檔案不存在時退回本通用模板。

## 輸出後處理

Ingestion pipeline 收到 LLM 輸出後:

1. 用 `extraction_output_schema.json` 驗證,失敗直接丟棄並記錄到 `ingestion_jobs.error_message`,不寫入 `curation_items`。
2. 驗證通過的輸出由 `ingestion/pipeline/group_statements.py` 切成**一個生物陳述一組**(P1 單一調控效果 / P2 分泌觸發 / P4 拮抗;剩餘的併成一組 residual)。每個 node/edge 寫入一筆 `curation_items`(`status = proposed`,`proposed_by = "llm"`),並帶上所屬的 `group_id`——群組才是人審核的單位。
3. 每組先過 Schema gate(`app/graph/engineer_gate.py`,只驗形式:型別白名單、id 慣例、三段式與 Interaction 完整性、back_translation 可讀性),再由專家審閱。
4. 後續審核走 `POST /admin/review/groups/{group_id}/approve|reject|gap`(見 `docs/api_contract.md` 與 `docs/expert-in-the-loop-workflow.md`)。

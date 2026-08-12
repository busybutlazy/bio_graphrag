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
3. 何時建立 RegulatoryEffect / Interaction 見下方規則 7、8,不要自行放寬。
   FeedbackLoop 只在文本描述「某效果會回頭影響觸發它自己的變因」的閉環時才建立;
   只有單向效果就建 RegulatoryEffect 即可。
4. 每個節點與關係都必須帶 source_chunk_id,對應到輸入文字的 chunk id。
5. 不確定的內容不要生成,寧缺勿濫。
6. 輸出必須是單一 JSON 物件,不要輸出 JSON 以外的文字、不要加註解、
   不要用 markdown code fence 包裹。形狀固定如下,**每個** node 與 edge 都必須
   帶齊全部欄位(少一個欄位,整段抽取都會被丟棄):

   {"nodes": [
      {"id": "hormone:insulin", "type": "Hormone", "label": "胰島素 / insulin",
       "description": "一到兩句說明", "source_chunk_id": "<本次 chunk_id>"}
    ],
    "edges": [
      {"id": "e:<chunk_id>:1", "type": "HAS_EFFECT",
       "source": "hormone:insulin", "target": "regulatory_effect:insulin_decreases_blood_glucose",
       "source_chunk_id": "<本次 chunk_id>"}
    ]}

   關係型別放在 edge 的 "type" 欄位(不是 "relationship");除上列欄位外,
   node 可選 "properties"、"possible_duplicate_of",edge 可選 "properties",
   不要自行新增其他欄位。
7. 關係有固定方向,不可自行調換。調控類一律走三段式,不可壓縮:

   Hormone ─HAS_EFFECT→ RegulatoryEffect ─ON_VARIABLE→ PhysiologicalVariable
                        RegulatoryEffect ─INCREASES|DECREASES→ PhysiologicalVariable

   正例(「胰島素會降低血糖濃度」):
     nodes: hormone:insulin, regulatory_effect:insulin_decreases_blood_glucose,
            physiological_variable:blood_glucose
     edges: hormone:insulin ─HAS_EFFECT→ regulatory_effect:insulin_decreases_blood_glucose
            regulatory_effect:insulin_decreases_blood_glucose ─ON_VARIABLE→ physiological_variable:blood_glucose
            regulatory_effect:insulin_decreases_blood_glucose ─DECREASES→ physiological_variable:blood_glucose

   常見錯誤,不要這樣寫:
     ✗ RegulatoryEffect ─HAS_EFFECT→ PhysiologicalVariable  (該位置用 ON_VARIABLE)
     ✗ Hormone ─DECREASES→ PhysiologicalVariable            (跳過 RegulatoryEffect)
     ✗ 只建立 RegulatoryEffect 而不建立造成它的 Hormone 節點

8. Interaction 必須引用**至少兩個**既有的 RegulatoryEffect:
   Interaction ─USES_EFFECT→ RegulatoryEffect (×2 以上)
   Interaction ─ON_VARIABLE→ PhysiologicalVariable
   還沒有兩個對應的 RegulatoryEffect 之前,不要建立 Interaction。

9. 節點 id 一律 <type_prefix>:<snake_case_name>,例如 hormone:insulin。
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

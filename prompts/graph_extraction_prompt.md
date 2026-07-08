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
3. 何時建立 RegulatoryEffect / Interaction / FeedbackLoop,嚴格依照
   extraction_guidelines.md 的判斷準則,不要自行放寬。
4. 每個節點與關係都必須帶 source_chunk_id,對應到輸入文字的 chunk id。
5. 不確定的內容不要生成,寧缺勿濫。
6. 輸出必須是單一 JSON 物件,完全符合 extraction_output_schema.json,
   不要輸出 JSON 以外的文字、不要加註解、不要用 markdown code fence 包裹。
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
2. 驗證通過的每個 node/edge,各自寫入一筆 `curation_items`(`status = proposed`,`proposed_by = "llm"`)。
3. 後續審核走 `POST /admin/curation/items/{item_id}/approve|reject`(見 `docs/api_contract.md` 第 3 節)。

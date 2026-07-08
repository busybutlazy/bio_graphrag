# Extraction Profiles(章節特化萃取 overlay)

每個 profile 是疊在 `prompts/graph_extraction_prompt.md`(通用 base)之上的一層
**章節特化補充**,用來告訴萃取 LLM「這一章應該重點抽出哪些 entity / relation」。

## 對應方式

document 掛一個 profile 名(`biology_sample_documents.json` 等來源的
`extraction_profile` 欄位)。萃取某文件的 chunk 時:

1. 讀 base system prompt(型別清單 + 通用判準)。
2. 若該文件的 `extraction_profile` 指到的 `<name>.profile.md` **存在於本地**,
   把它的內容當作章節特化補充,疊在 system prompt 後面。
3. 若欄位為空、或對應的 profile 檔不存在(例如公開 repo 沒有你的精雕檔),
   就**退回通用行為**——一樣能跑,只是少了章節重點提示。

組裝邏輯在 `ingestion/pipeline/build_extraction_prompt.py`。

## 公開 vs 本地

- `README.md`、`example.profile.md` 會進 git(格式展示用)。
- 其餘 `*.profile.md` 被 `.gitignore` 排除,**只存在你的本地**,是你的 IP。

新增精雕 profile:在本目錄建 `<你的章節名>.profile.md`,照 `example.profile.md`
的格式寫,不要 commit(gitignore 已擋)。

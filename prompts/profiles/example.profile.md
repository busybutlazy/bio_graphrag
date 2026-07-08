# Extraction Profile: example(可公開的格式範例)

這是 profile 的格式示範。真正的精雕 profile 請在同目錄另建
`<profile_name>.profile.md`,它們會被 `.gitignore` 排除、只存在你的本地。
以下每個區塊的內容都會被原樣接在 base system prompt 之後。

## 本章節萃取重點

- 優先 node type:(列出這一章最重要的節點型別,例如某章重 Hormone / Receptor /
  FeedbackLoop,另一章重 Structure / Process)
- 優先 relationship type:(列出這一章最重要的關係型別)
- 可略過:(這一章不太會出現、無需勉強抽的型別,降低雜訊)

## 章節特化判準

- (補充只適用本章、`schema/extraction_guidelines.md` 沒有涵蓋的判斷規則)

## few-shot 範例

- 輸入片段:(貼一小段本章代表性文字)
- 期望抽出:(對應的 node / edge,示範這章想要的網狀密度與重點)

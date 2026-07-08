# Code Review Report

> 日期：2026-07-08
> 審查基準 commit：abed176（`git rev-parse --short HEAD` 的結果）
> 分支：main
> 審查範圍：`abed176` 新增的「per-company vendor accounts」功能（17 個檔案）
> 審查模式：自訂範圍（聚焦本次 commit 的變更；先前 remediation 已於上一輪審查修復）
> 前次報告：codereview_2026-07-08_b6def96.md（b6def96）

## 摘要

- 審查檔案數：17（新審查：17，沿用前次：0）
- CRITICAL：0
- HIGH：0
- MEDIUM：2（本輪已修復 2）
- LOW：5（本輪已修復 3，已接受不改 2）
- 已修復（本輪）：5（2 MEDIUM + 3 LOW）；另 2 LOW 經使用者確認為已知取捨，不修改。詳見各項註記。

整體評語：此功能整體實作乾淨、邊界清楚——「預設關閉」的授權閘門、統一的 `TokenUsage` 計量、標準化錯誤格式與 `finally` 計費都落實正確，且有對應測試（60 passed）。無 CRITICAL/HIGH。以下發現多為健壯性與效能面的改善建議，符合履歷展示作品的定位，可依需求選擇性處理。

## 安全性發現

- [~] **[LOW]** 金鑰有效性可被回應碼區分（key-validity oracle）— **已接受不改**
  - **位置**：`backend/app/api/auth.py:58-67`
  - **描述**：未知金鑰回 `401 login_required`，但「存在但停用/到期」回 `403 account_disabled/expired`。回應碼不同，理論上可用來判斷某金鑰是否為真實存在的帳號。實務上金鑰為 `secrets.token_urlsafe(24)`（約 192 bits 熵），窮舉不可行，因此僅為資訊性風險。
  - **決策**：**維持現狀**。此 oracle 實質上是空的——攻擊者要看到 403 必須已持有一把真實（停用/到期）金鑰，而屆時差異化訊息並未透露他不知道的資訊；反之統一回 401 會讓真實廠商看到誤導訊息（帳號到期卻顯示「請登入」），是 UX 退步。差異化訊息對管理員/廠商較友善，故不修改。

- [~] **[LOW]** api_key 以明文儲存、前端存於 localStorage — **已接受不改**
  - **位置**：`ingestion/pipeline/schema.sql`（`vendors.api_key`）、`frontend/app.js`（`localStorage` 存取金鑰）
  - **描述**：金鑰明文入庫、前端存於 localStorage（XSS 可竊取）。README 已明確標註為 demo-grade access key，屬已知取捨。
  - **決策**（2026-07-08，使用者確認）：**維持明文並保留 README 註記**。雜湊儲存無法解決金鑰仍需經 TLS 傳輸與存於前端 localStorage 的部署層風險，且會使 `list` 無法顯示遮罩金鑰、金鑰遺失無法還原，屬超出 demo 範圍的擴張。正式化時再導入雜湊儲存與輪替。

## 邏輯正確性發現

- [x] **[MEDIUM]** `finally` 中的 `record_usage` 失敗會把「已成功且已計費」的回應變成 500
  - **位置**：`backend/app/api/routes_query.py:46-48`、`73-75`
  - **描述**：`record_usage` 位於 `finally`，若正常回應（`return QueryResponse(...)`）後，`record_usage` 因暫時性 DB 問題丟出例外，會覆蓋掉原本成功的回傳，使用者收到 500——即使答案已產生、token 已消耗。相較之下 `query_logs.log_query` 是 best-effort（自身包 try/except）。此處計費寫入未受保護，健壯性不一致。
  - **修復**：新增 `_record_usage_safe()`（`routes_query.py`）包 try/except 做 best-effort，兩個 endpoint 的 `finally` 改呼叫它，與 `log_query` 一致；記錄失敗不再拖垮已成功的回應。

- [x] **[LOW]** 配額為軟上限：即使單執行緒，最後一個請求也可能超額一整個請求量
  - **位置**：`backend/app/api/auth.py:66`
  - **描述**：閘門在請求「開始」時檢查 `tokens_used >= quota`；一旦通過即放行，該請求實際花費不設限。因此除了 README 已註明的並發超額外，單執行緒下最後一次放行也可能超出配額達「一個請求」的量。
  - **修復**：更新 README 的「soft cap」說明，明確指出「在請求開始時檢查，因此並發請求與跨越門檻的那一個請求都可能超額約一個請求的 token 量」，語意更精確。（行為屬設計取捨，維持不變。）

- [x] **[LOW]** CLI 對重複 vendor_code 或非法日期會拋出未處理例外
  - **位置**：`scripts/manage_vendors.py:32`（`date.fromisoformat`）、`scripts/manage_vendors.py:40`（`INSERT`，`vendor_code`/`api_key` UNIQUE）
  - **描述**：`add` 遇到重複 `--code`/`--key` 會由 asyncpg 丟 `UniqueViolationError`；`--expires` 格式錯誤會丟 `ValueError`。兩者都以裸 traceback 呈現給操作者，訊息不友善。
  - **修復**：`_parse_expires` 捕捉 `ValueError` → `SystemExit("invalid --expires ...: expected YYYY-MM-DD")`；`cmd_add` 捕捉 `asyncpg.UniqueViolationError` → `SystemExit("vendor_code ... or that --key already exists")`。已實測：重複 code 與壞日期都輸出友善訊息且非零退出。

## 效能發現

- [x] **[MEDIUM]** `require_vendor` 每次 token 請求做兩趟連續 DB 往返，且 `tokens_used` 為無上限的歷史 `SUM`
  - **位置**：`backend/app/api/auth.py:59,66`、`backend/app/db/vendors.py:46-51`
  - **描述**：授權流程先 `get_vendor`（一次 pool acquire）再 `tokens_used`（第二次 pool acquire），加上請求結束的 `record_usage` 與 `/query` 的 `log_query`，單一請求最多 4 趟連線取用。且 `tokens_used` 以 `SUM(tokens_used)` 掃描該 vendor 在 `vendor_usage` 的所有歷史列（已有 `vendor_code` index，僅掃該 vendor），隨用量累積成本線性成長。
  - **修復**：新增 `get_vendor_with_usage()`（`vendors.py`），以相關子查詢在同一 SQL 一次取回 vendor 欄位與 `used`；`require_vendor` 改用它，授權由 2 趟 pool acquire 降為 1 趟。已實測授權路徑仍正常（200）。歷史 `SUM` 成長屬 demo 規模可接受，running-total 留待未來。

## 可維護性發現

- [x] **[LOW]** 非 `APIError` 例外不套用標準化錯誤格式
  - **位置**：`backend/app/main.py:18-23`
  - **描述**：exception handler 只攔截 `APIError` 並輸出 `{"error":{"code","message"}}`；其餘未處理例外仍走 FastAPI 預設 `{"detail": "Internal Server Error"}`（500）。回應格式不一致。前端 `apiError` 有 fallback 到 `body.detail`，功能上不會壞，但契約不統一。
  - **修復**：新增泛用 `@app.exception_handler(Exception)`（`main.py`），未預期錯誤統一回 `{"error":{"code":"internal_error","message":...}}`（500），不洩漏內部細節。全套件 60 測試通過，確認未影響既有 4xx/422 路徑。

## 建議行動

本輪已全數處理，狀態如下：

1. ✅ **(MEDIUM)** `record_usage` 改為 best-effort（`_record_usage_safe`），與 `log_query` 一致。（`routes_query.py`）
2. ✅ **(MEDIUM)** `get_vendor_with_usage` 合併查詢，授權 DB 往返 2→1。（`auth.py` / `vendors.py`）
3. ✅ **(LOW)** `manage_vendors.py` 對重複 code／非法日期輸出友善訊息並非零退出。
4. ✅ **(LOW)** README soft-cap 語意補充「請求開始時檢查、可超額約一個請求量」。
5. ✅ **(LOW)** 新增泛用 `Exception` handler，500 也採標準錯誤格式。
6. ⏸ **(LOW)** key-validity oracle：已接受不改（實質為空的 oracle，統一 401 反而是 UX 退步）。
7. ⏸ **(LOW)** api_key 明文儲存：使用者確認維持明文並保留 README 註記（雜湊屬超出 demo 範圍的擴張）。

驗證：全套件 60 tests 通過；合併查詢授權、CLI 友善錯誤、標準錯誤格式均已對執行中的服務實測。

## 審查範圍限制

- 本次僅審查 `abed176` 引入的變更（vendor accounts 功能相關的 17 個檔案）；未重審此 commit 未觸及的既有程式碼（例如圖譜檢索、curation 服務等已於前次報告涵蓋）。
- 未進行動態滲透測試或負載測試；效能發現基於程式碼靜態分析與資料存取模式推論。
- 前端僅就本次 diff（登入控制、錯誤處理）審查，未全面重審既有 UI 邏輯。
- OpenAI 線上模式的實際 token 計量正確性以程式路徑確認（`response.usage.total_tokens`），未以付費 API 實跑驗證；離線模式已由測試涵蓋（0 token、不計費）。

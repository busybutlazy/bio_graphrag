進度

4. 計畫表（順序，不含時間）

順序: T1b<br>（現在，回到 T1）
項目: 巢狀 anchor 修正：anchor 不成為另一個 anchor 組的成員；連接兩 anchor 的邊歸 source 端
為什麼在這個位置: T1.5 的 stop condition，不修就不能進 T2
範圍: 本變更
────────────────────────────────────────
順序: T1c
項目: approve_group 補「邊端點必須存在（in-group 或 approved）」guard
為什麼在這個位置: 選 B 的前提；不補會寫出懸空的邊
範圍: 需擴大本變更範圍 → revision 3 重新批准
────────────────────────────────────────
順序: T2
項目: group-aware staging（原計畫）
為什麼在這個位置: 依賴 T1b 的切分規則定案
範圍: 本變更
────────────────────────────────────────
順序: T3
項目: 文件、前端揭露文字、完整驗證
為什麼在這個位置: 原計畫
範圍: 本變更
────────────────────────────────────────
順序: —
項目: 本變更結束、獨立審查、合併
為什麼在這個位置:
範圍:
────────────────────────────────────────
順序: N1
項目: Structured Outputs（json_schema + strict）+ 逐元素失敗而非整塊丟棄
為什麼在這個位置: 發現三。獨立於分組，但應排在下一次真實抽取之前，否則還會整章報銷
範圍: 新 change
────────────────────────────────────────
順序: N2
項目: 為 endocrine_demo_v1 寫 extraction profile：限定型別、講清楚 HAS_EFFECT／ON_VARIABLE 方向、附正確範例
為什麼在這個位置: 發現二。需要 N1 先穩住形式，才驗得出內容改善
範圍: 新 change（含一次花 token 的驗證）
────────────────────────────────────────
順序: N3
項目: 專家 lens 敘述品質：PART_OF 等簡單關係講成人話、重寫「請就內容本身審查」
為什麼在這個位置: 你上次選 A 延後的那個。與抽取無關，但殘餘組每章都會出現
範圍: 新 change（需一輪 grill 定義「哪些關係怎麼講」）
────────────────────────────────────────
順序: N4
項目: schema-gap backlog 生命週期（DF1）
為什麼在這個位置: grill 已定案延後，觸發條件：對真實章節記錄 gap 時
範圍: 新 phase
────────────────────────────────────────
順序: N5
項目: gold 改打真實抽取輸出（DF2）
為什麼在這個位置: 需要 N1+N2 讓抽取品質穩定後才有意義
範圍: P5 收尾
────────────────────────────────────────
順序: N6
項目: 稽核 actor 由 admin key 決定（S1）
為什麼在這個位置: 上一輪審查定為獨立 Phase，含契約變更與 /admin 上線姿態
範圍: 新 phase
────────────────────────────────────────
順序: N7
項目: 群組審閱的部分處置：residual 組逐項處置、pattern 組「修正後核准」；一併關掉 approve_item 繞過 gate 的路徑
為什麼在這個位置: 2026-08-12 發現。pattern 組（P1/P2/P4/P6）本身就是一條陳述，部分核准會讓圖譜內容與專家核准的那句話不一致，正解是「改了再核准」——但 service 只有 create/approve/reject，沒有 update，所以今天只能退回重提。residual 組不是陳述（lens 自己渲染成「不屬於任何已知的調控模式」），整包丟棄純屬浪費，逐項處置沒有原子性要守。另 approve_item（service.py:247）無 group 意識，會把單一成員直接寫進 Neo4j，繞過 Schema gate、反向翻譯、deprecated 與懸空邊兩道防線；前端未呼叫該端點且 /admin 暫不對外開放，故非緊急，但 N6 上線前必須關掉
範圍: 新 change（需一輪 grill 定義部分處置的邊界）
狀態: **後門已關（`changes/close-approve-item-backdoor`，2026-08-13）。部分處置仍未做。**
關掉的比原本記的更多：後門不只 `approve_item`，而是「`create_item` 產生沒有 `group_id`、
審閱佇列看不見的列」＋「`approve_item` 只憑 `status=='proposed'` 就寫進 Neo4j」兩個缺口串成的
**完整平行路徑**。三個寫入端點（`POST /admin/curation/items`、`.../approve`、`.../reject`）已整條移除，
`GET` 保留。進入圖譜現在只有群組端點一個入口。
**仍未做**：residual 組逐項處置、pattern 組「修正後核准」（service 沒有 update，今天仍只能退回重提）。
那部分照原記載需要一輪 grill 定義邊界，**N7 不能因後門關掉而視為完成**。
────────────────────────────────────────
順序: N8
項目: 長時間 ingest 的請求形態:POST /admin/ingest/run 目前是同步阻塞,四個 chunk 就要約 4 分鐘,超過 nginx 預設代理逾時
為什麼在這個位置: 2026-08-12 實際踩到。nginx 回 504 但後端仍跑完,操作者(或 agent)誤判為失敗而重試,造成第二次抽取同時在跑並重複花費約 15–25k tokens。這不是偶發失誤而是介面設計問題:一個會花錢、耗時數分鐘的操作,卻用「同步等待、逾時就沒有回應」的形態暴露出去。三個方向擇一——(a) 只調高 nginx 逾時(最小,但治標);(b) 改為非同步:回 job_id + 輪詢 /admin/ingest/jobs/{id}(治本,但是契約變更);(c) 在後端加同來源進行中 job 的併發防護(讓重試變成無害)。實務上 (c) 最能防止重複扣款,因為它不依賴操作者判讀正確
範圍: 新 change（含契約決策；(b) 會動到 docs/api_contract.md 與前端匯入頁）
狀態: **(c) 已完成**（`changes/ingest-concurrency-guard`，2026-08-13）。同來源已有進行中的抽取 job 時，
`POST /admin/ingest/run` 在花掉任何 token 之前回 `409 ingest_already_running`，訊息含擋住的 job_id
與「不要重試」。實作為 `ingestion_jobs` 上的部分唯一索引（連線無關），孤兒列 2 小時後自動失效。
**(a) 與 (b) 仍未做**：504 本身還在，操作者仍會看到逾時，只是重試不再扣款。真正的解法是 (b) 非同步化
（回 job_id + 輪詢），它是契約變更且要改前端匯入頁，留待獨立變更。
────────────────────────────────────────
順序: N9
項目: ingest 併發防護的審查殘留項（`changes/ingest-concurrency-guard` REVIEW_REPORT，2026-08-13）
為什麼在這個位置: 該次審查無 Blocking/High；M-1（409 文案在孤兒情境給反向指示）與 S-1（前綴耦合無守衛）已於同一分支修掉，以下為刻意延後的項目。都不緊急，但都是「測試全綠卻靜默失效」或「訊息誤導操作者」這一類，值得在下次動到 ingest 時一併處理：
  - **L-1 防護鍵是 `source_path`，破壞性寫入鍵是 `doc_id`**。兩個不同來源檔可以有相同 `doc_id`（front-matter 手寫撞名，或 sample/private 同 stem），此時防護放行，兩次抽取各自 `delete_chunks_for_doc(doc_id)` → `upsert_chunks`，後到的 delete 可能清掉先到者剛寫好的 chunks（PG 與 Qdrant 皆然）。是資料一致性缺口，非重複扣款。最小處置：`docs/api_contract.md` 第 3 點補一句「前提是兩來源 `doc_id` 不同」；根治要把防護鍵改成 `doc_id` 或加 doc_id 唯一性檢查。
  - **L-2 claim 的 INSERT 失敗與查詢之間有毫秒窗口**：擋住的 job 若剛好在此期間結束，訊息退化成 `job_id=None、開始於 未知時間`，卻仍叫人不要重試——而此刻重試會成功。處置：`blocking is None` 時重試一次 claim。
  - **L-3 HTTP 測試在真實 demo 章節路徑上留 `running` 列**（`test_run_refuses_a_second_ingest_of_the_same_source`），只靠 `finally` 清。pytest 被硬殺時開發機的 demo 章節會被鎖 2 小時，症狀與真實事故無法區分。處置：改用不對應真實檔案的 source_path。
  - **S-2 `_second_connection()` 逐字複製了 `conftest.py::pg_conn` 的連線參數**。conftest 若改來源，這裡不會跟著改，「兩條連線指向同一個 DB」會靜默變假而測試仍過。處置：把連線工廠抽到 conftest 共用。
  - **S-3 `ensure_schema` 每次啟動與每次 `/admin/ingest/run` 都跑一次全表 UPDATE**。目前約 100 列可忽略，此表只增不減；成長後再收斂為「索引不存在時才跑」。現階段 YAGNI，不要動。
  - **既有觀察（先於本變更，未實測，兩種結果皆可能）**：`runner.py` 的 `except Exception` 抓不到 `CancelledError`。優雅取消時 `finally` 若跑完，會用初始值 `status="success"` 收尾，把被中斷的 job 記成成功（稽核紀錄說謊，但鎖有被釋放）；若 `finally` 裡的 `await finish_ingestion_job(...)` 本身也被取消打斷，該列就留在 `running`，**鎖被洩漏 2 小時**。取決於取消時機，**不要假設方向是安全的**。（審查 N-3 指出我原本只寫了前一半。）
範圍: 後續 change（可拆，皆為小範圍）

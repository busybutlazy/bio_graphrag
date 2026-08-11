# Verification Report: extract-per-group-staging

## Result

- Overall: **Pass** on everything automatable. **One item owed**: a browser confirmation that the
  Ingestion page's rewritten notice reads correctly and that extracted groups appear in 群組審閱
  （前端無測試 harness)。所有等價行為已在容器內以端到端執行驗證（見下)。
- Environment: branch `feat/extract-per-group-staging`,基於 `main` @ `0a3e5be`。
  Docker/Compose;ruff `ghcr.io/astral-sh/ruff:0.15.21`;mypy 1.15.0（host,`make lint` 亦然)。
  **離線姿態**（`-e OPENAI_API_KEY=`)——本變更的所有自動化驗證零 token。
- 計畫 revision 3,執行順序 T1 → T1.5（owner,線上)→ T1b → T1c → T2 → T3。

## Requirement Traceability

| Acceptance criterion | Implementation | Test / observation | Result |
|---|---|---|---|
| AC1 兩個 RE 共用一變數 → 2 組,共用節點同時在兩組 | `group_statements.split_into_statements` | `test_two_statements_split_and_share_their_common_variable` | Pass |
| AC1b 巢狀 anchor 互不包含 | `_edge_owner` + anchor 不納入 | `test_nested_anchors_reference_each_other_instead_of_absorbing`、`test_real_extraction_output_splits_without_anchor_cross_contamination` | Pass |
| AC1c 端點不存在 → 409,Neo4j 未寫入;現有群組無回歸 | `approve_group` 第六道防線 | `test_approve_refuses_an_edge_endpoint_that_exists_nowhere`、`test_approve_succeeds_once_the_referenced_nodes_are_approved`、`test_existing_groups_still_approve_under_the_endpoint_guard`;live 佇列 7/7 通過 | Pass |
| AC2 殘餘組;無殘餘則不產生 | `split_into_statements` 尾段 | `test_no_anchor_yields_a_single_residual_group`、`test_mixed_chunk_splits_into_pattern_group_plus_residual`、`test_two_statements_...`（斷言無殘餘組) | Pass |
| AC3 群組可見於 `list_groups`,gate 與句子正確 | `stage_extraction_output` 寫 `group_id` | `test_extracted_statements_reach_the_group_review_queue`;另有端到端實跑（下) | Pass |
| AC4 已 approved 節點只引用不提案 | `approved_ids` 過濾 | `test_already_approved_nodes_are_referenced_not_reproposed` | Pass |
| AC5 重跑冪等（列數與群組數不增) | 確定性 `group_id` | `test_re_ingest_does_not_duplicate_the_review_queue` | Pass |
| AC6 抽取路徑不寫 Neo4j | 未變更 | 端到端實跑後查詢提案 id → 0 列;`app.eval.runner` PASS（檢索未退化) | Pass |
| AC7 套件、lint、type、node --check、文件 | — | 見下方命令 | Pass |
| AC8 前端揭露文字移除 + `?v=` bump;`api_contract.md` 同步 | `app.js`、`index.html`、`api_contract.md` | `node --check` OK;**瀏覽器確認owed** | Partial（owed) |

## Commands Executed

```
docker compose run --rm -e OPENAI_API_KEY= backend pytest tests ingestion/tests -q
  → 186 passed in 74.97s   （main baseline 183 + 3 新增;T1/T1b/T1c/T2 期間逐步累積)

docker compose run --rm -e OPENAI_API_KEY= backend python -m app.eval.runner
  → Recall@5 1.0 (門檻 0.8) · Grounded 1.0 (門檻 0.75) · P95 284.6ms (門檻 5000ms) · Overall PASS

ruff 0.15.21 check / format --check (LINT_PATHS)  → All checks passed / 101 files
mypy backend/app ingestion scripts                → Success: no issues found in 79 source files
node --check frontend/app.js                      → OK
```

**端到端（離線,注入式 extractor,真實三個資料庫）**——本變更的核心主張:

```
抽取統計: {'chunks': 1, 'proposed_nodes': 4, 'proposed_edges': 3, 'proposed_groups': 2}

群組審閱佇列裡的抽取群組:
  * 000:regulatory_effect:e2e_low
      gate: pass | 「E2E胰島素會造成一個調控效果:使E2E血糖下降。」
  * 000:residual
      gate: pass | 「本提案描述了E2E誤解等概念及其關係,但不屬於任何已知的調控模式;請就內容本身審查。」
```

在此變更之前,同一份輸出會寫成 7 筆未分組 items,`list_groups` **一筆都看不到**。

## Regression Evidence

兩處刻意做了反向驗證,證明測試不是套套邏輯:

- **漂移守衛**:`PATTERN_ANCHOR_TYPES` 移除 `Interaction` → `test_pattern_anchor_types_...` 失敗。
- **端點 guard**:改成 `if False and missing:` → `test_approve_refuses_an_edge_endpoint_that_exists_nowhere`
  失敗,且該次執行**真的把 anchor 寫進 Neo4j**（懸空的邊)。殘留已清除並納入 teardown。

## Owed / Not Run

- **瀏覽器確認**（前端無 harness):收錄頁改寫後的說明文字、以及抽取後群組出現在 群組審閱 頁。
- **CI 未跑**（尚未 push)。
- **未再花 token 重跑真實抽取**:T1.5 已完成觀察並據以修正（T1b);T2/T3 的行為以離線注入式
  extractor 覆蓋。真實抽取的**語意品質**問題（見 CHANGE_REPORT 的 R7)未在本次處理。

## Environment Notes（既有,非本變更）

- `scripts/wait_for_services.sh` 探測未開放的 8000 埠會誤報逾時;`make health` 為可用檢查。
- `mypy` 不在 backend image 內,`make lint` 於 host 執行。
- Neo4j 在 Raspberry Pi 上啟動需 1–3 分鐘,期間 `/admin/*` 會回 502——非缺陷。

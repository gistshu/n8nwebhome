# 對話摘要（最新）

## 目標
建立三個可串接 n8n webhook 的查詢頁面，並持續優化成可實際展示與操作的多頁面介面。

## 目前頁面與定位
- `index.html`：IVF預約統計查詢(2022年)
- `tcm-consult.html`：中醫診斷用藥建議(醫師使用)
- `hr-qa.html`：人資辦法Q/A

## 已完成功能
1. 三頁切換與共通 UI
- 每頁上方有 `n8n 測試 網頁 title`
- 三個按鈕可切換頁面
- 查詢按鈕文字統一為「查詢」

2. webhook 串接
- 每頁以 `POST` 傳送 JSON 到各自 webhook
- request body 包含：`question`、`sessionId`、`sentAt`
- 支援回應格式：`{ "success": true/false, "reply": "..." }`

3. Session 機制
- 每個功能獨立 session（localStorage key 不同）
  - IVF：`n8n_session_ivf_2022`
  - 中醫：`n8n_session_tcm_consult`
  - 人資：`n8n_session_hr_qa`

4. 回答顯示方式
- 問答以對話氣泡顯示並持續 append
- 回答區固定高度、可捲動（避免頁面無限拉長）
- 中醫頁右側查詢紀錄可點選，點選後會回填左側問題並顯示中央回答內容

5. 版面配置
- 中醫頁桌機寬度：`90vw`
- 中醫頁三欄比例：`30% / 50% / 20%`
- 手機 RWD（`max-width: 900px`）滿版
  - `body` 無留白
  - `.card` 使用 `100vw`，並移除左右邊框與圓角

6. 文案調整
- 中醫頁標題改為：`中醫診斷用藥建議(醫師使用)`
- 中醫頁欄位「你的問題」改為「客人診狀」

7. 正式 webhook URL 對應
- 人資：`http://localhost:5678/webhook/bc8b8b7a-34cd-49d0-9519-825a141a3c76`
- IVF：`http://localhost:5678/webhook/dcafced2-af3e-4c8a-bf9f-857646cde22c`
- 中醫：`http://localhost:5678/webhook/07d6d928-54fe-49d8-bec5-df537fff43c2`

8. 預設範例資料（開頁即顯示）
- IVF 頁：
  - 問題：`請統計2022年30歲以上的預約人數`
  - 回答：`2022年30歲以上的預約人數為360人。`
- 中醫頁：
  - 問題：`34歲，女性，不孕三年，無IVF經驗`
  - 回答：已預設完整長文範例（含調理項目與追問）
- 人資頁：
  - 問題：`公司績效制度`
  - 回答：已預設完整長文範例（含制度重點條列）

9. 中醫頁 PostgreSQL 紀錄功能
- `tcm-consult.html` 目前改由本地 `app.py` 處理
- `app.py` 會：
  - 呼叫中醫 n8n webhook 取得回答
  - 直接寫入 PostgreSQL `tcm_consult_logs`
  - 讀取指定醫師最近 10 筆問答紀錄
- 紀錄欄位包含：
  - `doctor_name`
  - `question`
  - `reply`
  - `execution_seconds`
  - `asked_at`
- 右側查詢紀錄顯示指定醫師最近 10 筆問答資料

10. 中醫頁本次優化
- 查詢按鈕右方新增 n8n 執行秒數顯示
- 中央回答區固定為三個區塊呈現：
  - `診斷建議（Assessment／評估）`
  - `用藥方案建議（Plan／計畫）`
  - `調養方案建議（Plan／計畫）`
- n8n 回覆若使用 Markdown 標題格式，例如：
  - `### 診斷建議（Assessment／評估）`
  - `### 用藥方案建議（Plan／計畫）`
  - `### 調養方案建議（Plan／計畫）`
  會自動解析並顯示到對應中央區塊
- 若回覆未明確分段，前端會以段落與關鍵字做 fallback 分類
- 點選右側歷史紀錄時，會同步顯示：
  - 左側問診資訊
  - 中央三個回答區塊的對應內容
  - 該筆執行秒數

11. 2026-06-21 文案更新
- `tcm-consult.html` 左側輸入欄標籤由 `請輸入 問診資訊` 改為 `請輸入 問診資訊(S/O)`
- `tcm-consult.html` 中央欄標題由 `AI 資料庫RAG查詢(A/P)` 調整為 `AI 資料庫RAG查詢`

12. 2026-06-22 中醫頁顯示規則更新
- 中醫頁中央欄不再顯示單一整段回覆，而是固定顯示三個結果卡片
- 右側歷史紀錄點選後，會套用與最新查詢結果相同的解析規則
- 已支援依下列標題格式對應顯示：
  - `### 診斷建議（Assessment／評估）`
  - `### 用藥方案建議（Plan／計畫）`
  - `### 調養方案建議（Plan／計畫）`

## 啟動方式
- 啟動本地整合服務：
  - `python3 app.py`
- 開啟：
  - `http://127.0.0.1:8000/tcm-consult.html`

## PostgreSQL
- 預設連線字串：`dbname=postgres user=shushu`
- 可用環境變數覆蓋：
  - `PG_DSN`
  - `N8N_TCM_WEBHOOK_URL`
  - `APP_HOST`
  - `APP_PORT`

## 相關摘要檔
- `conversation-summary.md`：本檔（已更新）
- `conversation-summary.html`：先前由 md 轉出的 HTML 版本

# SITCON 2026 指南針計畫(月老計畫) 配對腳本

---

## 開發環境

- Python 3.10+
- uv

---

## 架構介紹

```shell
# |- input (放 會眾/工人資料)
# |- output (放配對結果)
# |- const.py 常數
# |- normalize_submission_columns.py 標準化會眾報名資料欄位（LLM 輔助）
# |- normalize_staff_submission_columns.py 標準化工人報名資料欄位（LLM 輔助）
# |- preprocess_attendees.py 預處理會眾資料
# |- preprocess_workers.py 預處理工人資料
# |- merge_and_group.py 配對腳本
```

## 使用方法

### 1. 下載 會眾資料/工人/講者資料

會眾資料 下載到 input/attendees.xlsx
工人/講者資料 下載到 input/workers.xlsx

### 2. 安裝套件

```shell
uv sync
```

### 3. (選用) 執行欄位標準化腳本 (LLM 輔助)

若需要將原始報名表單（CSV 格式）中的學校/單位、系所/職稱、聯絡方式等文字欄位進行標準化（例如統一不同寫法的機構名稱），可使用此腳本。此腳本透過呼叫 OpenAI 兼容的 LLM API 進行資料清理。

1. 在專案根目錄建立 `.env` 檔案並設定 API 環境變數：
   ```env
   OPENAI_BASE_URL="你的 API Base URL" # 若使用 OpenAI 官方 API 可省略
   OPENAI_API_KEY="你的 API Key"
   OPENAI_MODEL="gpt-4o-mini"
   ```

2. 將原始 CSV 報名資料放置於專案根目錄：
   - 會眾資料：命名為 `submissions.csv`
   - 工人資料：命名為 `staff-submissions.csv`

3. 執行腳本：
   ```shell
   # 標準化會眾資料
   uv run python normalize_submission_columns.py # 得到 submissions.standardized.csv 與狀態暫存 standardized_names.json
   
   # 標準化工人資料
   uv run python normalize_staff_submission_columns.py # 得到 staff-submissions.standardized.csv 與狀態暫存 staff_standardized_names.json
   ```
   > **注意**：
   > - 處理過的結果會存在 json 中（`standardized_names.json` / `staff_standardized_names.json`），具有斷點續傳特性，重新執行將沿用先前的標準化結果，不需重複消耗 Token。
   > - 處理完成後，可再將 `*.standardized.csv` 自行整理匯出為 `input/attendees.xlsx` 與 `input/workers.xlsx` 以進行後續步驟。

### 4. 執行 Preprocess 會眾/工人/講者 資料

這邊主要是讓兩張表格式統一、生成指標與進行 One-hot encoding 好讓後續配對

```shell
uv run python preprocess_attendees.py # 得到 output/1/attendees.xlsx
uv run python preprocess_workers.py # 得到 output/1/workers.xlsx
```

### 5. 執行配對腳本

```shell
uv run python merge_and_group.py # 得到 output/SITCON_2026_Compass_Groups.xlsx
```

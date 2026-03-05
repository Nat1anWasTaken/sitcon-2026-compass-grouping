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

### 3. 執行 Preprocess 會眾/工人/講者 資料

這邊主要是讓兩張表格式統一、生成指標與進行 One-hot encoding 好讓後續配對

```shell
uv run python preprocess_attendees.py # 得到 output/1/attendees.xlsx
uv run python preprocess_workers.py # 得到 output/1/workers.xlsx
```

### 4. 執行配對腳本

```shell
uv run python merge_and_group.py # 得到 output/SITCON_2026_Compass_Groups.xlsx
```

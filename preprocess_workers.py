import pandas as pd
from const import community_member_count_mapping, interaction_mapping, experience_mapping,experience_list_zh

file_path = "input/workers.xlsx"
output_file_path = "output/1/workers.xlsx"
df = pd.read_excel(file_path)


def process_worker_data(df):
    processed_df = pd.DataFrame()

    # A. 基礎資料
    processed_df['Email'] = df['聯絡用 email']
    processed_df['暱稱'] = df['暱稱或姓名']
    processed_df['單位'] = df['目前所在的單位 ( ex: 學生: 校名/系級 ; 社會人士: 工作單位/部門或職稱類型 )']
    processed_df['身分別'] = df['您此次年會的身分別'].fillna('未知')
    processed_df["聯絡方式"] = df['其他可提供給對方的聯絡方式 (至少一種)'].fillna('無')

    # B. 順序編碼 (數值化)
    # 指標 8: 經驗平衡
    processed_df['會眾分數'] = df[
        '請問您以會眾身分參加過實體社群活動 (如: SITCON , HITCON , COSCUP 等) 的次數?'].map(
        community_member_count_mapping).fillna(0)
    processed_df['工人分數'] = df[
        '請問您以工人/講者/贊助商/社群單位身分參加過社群 (如: SITCON , HITCON , COSCUP 等) 的次數?'].map(
        community_member_count_mapping).fillna(0)
    processed_df['社群分數'] = processed_df['會眾分數'] + processed_df['工人分數']

    # 指標 6: 互補個性 [cite: 146, 147]
    processed_df['交流分數'] = df[
        '假設當天在 SITCON 年會會場，有不認識的陌生人想跟您交流/交談時，我通常...'].map(interaction_mapping).fillna(2)

    # 指標 7: 認真程度 (字數統計)
    processed_df['自我介紹長度'] = df['給對方的自我介紹、想說的話或想學到的內容 (約 15 ~ 50 字)'].astype(
        str).str.len().fillna(0)

    # D. 複選題處理：轉換為英文欄位名並統計 0/1
    # 處理「已經了解或經驗」(指標 4: 專業能力) [cite: 139]
    exp_col_name = '您對下列哪些項目已經有了解或經驗呢?（複選）'
    for zh_name, en_name in experience_mapping.items():
        # 欄位名稱轉為英文，例如 Has_Exp_Front_end_Engineering
        col_key = f"有經驗_{en_name.replace(' ', '_').replace('/', '_')}"
        processed_df[col_key] = df[exp_col_name].str.contains(zh_name, na=False).astype(int)

    # 處理「想了解或學習」(指標 3: 興趣相同) [cite: 137]
    learn_col_name = '下列哪些項目是您還沒有接觸過，但想了解或學習的呢?\n（複選）'
    for zh_name, en_name in experience_mapping.items():
        # 欄位名稱轉為英文，例如 Want_Learn_Artificial_Intelligence
        col_key = f"想學_{en_name.replace(' ', '_').replace('/', '_')}"
        processed_df[col_key] = df[learn_col_name].str.contains(zh_name, na=False).astype(int)

    return processed_df


# 執行
encoded_worker_df = process_worker_data(df)
encoded_worker_df.to_excel(output_file_path, index=False)
print("工人表單 Encoding (英文欄位) 完成！")
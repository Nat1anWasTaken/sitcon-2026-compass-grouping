import pandas as pd
from const import community_member_count_mapping, interaction_mapping, experience_mapping,experience_list_zh

file_path_attendee = "input/attendees.xlsx"
output_file_path = "output/1/attendees.xlsx"
df_a = pd.read_excel(file_path_attendee, sheet_name='編輯區')
experience_list_en = list(experience_mapping.values())

def process_attendee_data(df):
    processed_df = pd.DataFrame()

    # A. 基礎資料對齊
    processed_df['Email'] = df['Email']
    processed_df['暱稱'] = df['暱稱']
    processed_df['單位'] = df['學校 / 單位名稱']
    processed_df['身分別'] = '會眾'
    processed_df["聯絡方式"] = df['其他可提供給對方的聯絡方式（至少一種）']

    # B. 數值化編碼
    # 處理參加次數 (指標 8) [cite: 151]
    # 注意：會眾表單的題目文字可能多了一個問號或空白，建議用 str.contains 或精確複製
    col_a_count = '請問您以會眾身分參加過實體社群活動（如：SITCON , HITCON , COSCUP 等）的次數？'
    col_s_count = '請問您以工人/講者/贊助商/社群單位身分參加過社群（如：SITCON , HITCON , COSCUP 等）的次數？'

    processed_df['會眾分數'] = df[col_a_count].astype(str).str.strip().map(
        community_member_count_mapping).fillna(0)
    processed_df['工人分數'] = df[col_s_count].astype(str).str.strip().map(
        community_member_count_mapping).fillna(0)
    processed_df['社群分數'] = processed_df['會眾分數'] + processed_df['工人分數']

    # 處理交流意願 (指標 6) [cite: 146]
    col_interact = '假設當天有陌生人想跟您交流，您通常……'
    processed_df['交流分數'] = df[col_interact].astype(str).str.strip().map(interaction_mapping).fillna(2)

    # 指標 7: 認真程度 [cite: 148]
    col_intro = '給對方的自我介紹、想說的話或想學到的內容（約15～50字）。'
    processed_df['自我介紹長度'] = df[col_intro].astype(str).str.len().fillna(0)

    # C. 複選題處理 (轉英文並統計 0/1) [cite: 137, 139]
    # 專業能力 (指標 4)
    exp_col = '您對下列哪些項目已經有一些了解或經驗呢？'
    for zh_name, en_name in experience_mapping.items():
        col_key = f"有經驗_{en_name.replace(' ', '_').replace('/', '_')}"
        processed_df[col_key] = df[exp_col].str.contains(en_name, na=False).astype(int)

    # 想學興趣 (指標 3)
    want_col = '下列哪些項目是您還沒有接觸過，但想了解或學習的呢？'
    for zh_name, en_name in experience_mapping.items():
        col_key = f"想學_{en_name.replace(' ', '_').replace('/', '_')}"
        processed_df[col_key] = df[want_col].str.contains(en_name, na=False).astype(int)

    return processed_df


# 執行
encoded_attendee_df = process_attendee_data(df_a)
encoded_attendee_df.to_excel(output_file_path, index=False)
print(f"會眾表單處理完成，共 {len(encoded_attendee_df)} 人參與指南針計畫。")
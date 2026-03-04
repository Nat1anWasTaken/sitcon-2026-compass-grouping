import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

# 1. 讀取已 Encoding 的資料
df_workers = pd.read_excel("output/1/workers.xlsx")
df_attendees = pd.read_excel("output/1/attendees.xlsx")

# 合併兩張表
df_total = pd.concat([df_workers, df_attendees], ignore_index=True).reset_index(drop=True)
output_file_path = 'output/SITCON_2026_Compass_Groups.xlsx'

def generate_groups(df, group_size=4):
    people = df.to_dict('records')
    unassigned = list(range(len(people)))
    groups = []

    # 取得專業能力與想學項目的欄位清單 (用於指標 3 & 4) [cite: 137, 139]
    exp_cols = [c for c in df.columns if '有經驗_' in c]
    want_cols = [c for c in df.columns if '想學_' in c]

    while len(unassigned) >= 3:
        # 優先挑選認真的人作為種子 (指標 7) [cite: 148, 150]
        unassigned.sort(key=lambda idx: people[idx]['自我介紹長度'], reverse=True)
        seed_idx = unassigned.pop(0)
        current_group = [seed_idx]

        while len(current_group) < group_size and unassigned:
            best_score = -float('inf')
            best_candidate_idx = -1

            for candidate_idx in unassigned:
                score = 0
                p1 = people[current_group[0]]
                p2 = people[candidate_idx]

                # 指標 1 & 2: 單位避震 (同單位扣分) [cite: 129, 132]
                if str(p1['單位']).strip() == str(p2['單位']).strip():
                    score -= 50

                # 指標 3 & 4: 興趣與專業相似度 [cite: 137, 139]
                v1 = [p1[c] for c in exp_cols + want_cols]
                v2 = [p2[c] for c in exp_cols + want_cols]
                if sum(v1) > 0 and sum(v2) > 0:
                    score += cosine_similarity([v1], [v2])[0][0] * 10

                # 指標 6: 個性互補 (主動型配內向型) [cite: 146]
                if abs(p1['交流分數'] - p2['交流分數']) >= 2:
                    score += 5

                # 指標 7: 認真程度接近 [cite: 148]
                if abs(p1['自我介紹長度'] - p2['自我介紹長度']) < 10:
                    score += 3

                # 指標 8: 經驗平衡 (老手帶新手) [cite: 151, 153]
                if abs(p1['社群分數'] - p2['社群分數']) >= 3:
                    score += 5

                if score > best_score:
                    best_score = score
                    best_candidate_idx = candidate_idx

            if best_candidate_idx != -1:
                current_group.append(best_candidate_idx)
                unassigned.remove(best_candidate_idx)
            else:
                break
        groups.append(current_group)

    # 處理剩下的人 (補入現有小組)
    for i, idx in enumerate(unassigned):
        groups[i % len(groups)].append(idx)

    return groups


# 執行分組
group_indices = generate_groups(df_total)

# 2. 整理結果輸出 (將組別放在第一欄)
result_rows = []
for i, group in enumerate(group_indices):
    for member_idx in group:
        p = df_total.iloc[member_idx].copy()
        # 建立一個新的字典，將「組別」放在第一個位置
        new_row = {'組別': f"Group_{i + 1:02d}"}
        new_row.update(p.to_dict())
        result_rows.append(new_row)

df_result = pd.DataFrame(result_rows)


# 3. 定義顏色標記邏輯
def style_groups(df):
    # 柔和的粉彩色系
    colors = ['#EBF5FB', '#FEF9E7', '#EAFAF1', '#FBEEE6', '#F4ECF7', '#FDEDEC', '#E8F8F5']
    style_df = pd.DataFrame('', index=df.index, columns=df.columns)

    unique_groups = df['組別'].unique()
    group_color_map = {group: colors[i % len(colors)] for i, group in enumerate(unique_groups)}

    for idx, row in df.iterrows():
        color = group_color_map[row['組別']]
        style_df.loc[idx, :] = f'background-color: {color}'
    return style_df


# 4. 輸出結果
try:
    # 這裡需要安裝 jinja2 才能輸出顏色樣式 (uv add jinja2)
    styled_df = df_result.style.apply(style_groups, axis=None)
    styled_df.to_excel(output_file_path, index=False, engine='openpyxl')
    print(f"✅ 成功！分組結果已儲存至 {output_file_path}")
except Exception as e:
    print(f"樣式套用失敗 (可能是缺少 jinja2)，已輸出純文字版。錯誤：{e}")
    df_result.to_excel(output_file_path, index=False)
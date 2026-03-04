community_member_count_mapping = {
    # ZH-TW
    "未參加過": 0,
    "1~2次": 1,
    "3~4次": 3,
    "5次(含)以上": 5,
    # EN
    "Never participated":0,
    "1–2 times":1,
    "3–4 times":3,
    "5 times or more":5,
}

interaction_mapping = {
    # ZH-TW
    '總是可以主動跟陌生人交談': 4,
    '常常主動跟陌生人交談': 3,
    '不主動但對方先跟我交談時，我會積極與對方討論': 2,
    '不主動且對方先跟我交談時，我不知如何與對方溝通': 1,
    # EN
    'Not proactive and unsure how to communicate when someone talks to me first':1,
    'Not proactive but will actively engage in discussion when someone talks to me first': 2,
    'Often initiates conversations with strangers': 3,
    'Always able to proactively start conversations with strangers': 4,
}

experience_mapping = {
    "前端工程":"Front-end Engineering",
    "後端工程":"Back-end Engineering",
    "測試工程":"Testing/QA",
    "行動裝置開發":"Mobile Development",
    "遊戲開發":"Game Development",
    "DevOps/SRE":"DevOps/SRE",
    "韌體/電子電路":"Firmware/Electronic Circuits",
    "區塊鏈":"Blockchain",
    "人工智慧":"Artificial Intelligence",
    "資料科學":"Data Science",
    "網路通訊":"Network Communication",
    "專案管理" :"Project Management",
    "資訊安全":"Information Security",
    "社群經營":"Community Management",
    "視覺、動畫設計":"Visual/Animation Design",
    "程式競賽":"Programming Competitions"
}
experience_list_zh = list(experience_mapping.keys())
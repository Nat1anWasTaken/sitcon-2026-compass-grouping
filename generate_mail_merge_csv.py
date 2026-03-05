from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

INPUT_CSV_PATH = Path("merged-result.csv")
TEMPLATE_PATH = Path("members-template.txt")
OUTPUT_CSV_PATH = Path("mail-merge.csv")
STAFF_DATA_PATH = Path("staff-data.csv")
PARTICIPANTS_DATA_PATH = Path("participants-data.csv")
AREA_MAPPING_PATH = Path("area-mapping.json")

GROUP_COL = "組別"
EMAIL_COL = "Email"
NICKNAME_COL = "暱稱"
CONTACT_COL = "聯絡方式"
WANT_PREFIX = "想學_"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate mail-merge CSV from merged-result.csv with columns: "
            "receipt, recipient_name, members_string"
        )
    )
    parser.add_argument("--input", type=Path, default=INPUT_CSV_PATH)
    parser.add_argument("--template", type=Path, default=TEMPLATE_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_CSV_PATH)
    parser.add_argument("--staff-data", type=Path, default=STAFF_DATA_PATH)
    parser.add_argument("--participants-data", type=Path, default=PARTICIPANTS_DATA_PATH)
    parser.add_argument("--area-mapping", type=Path, default=AREA_MAPPING_PATH)
    return parser.parse_args()


def normalize_area_key(value: str) -> str:
    return value.replace(" ", "_").replace("/", "_")


def find_col_by_candidates_or_keyword(
    df: pd.DataFrame,
    candidates: list[str],
    keyword: str,
    file_label: str,
    field_label: str,
) -> str:
    for col in candidates:
        if col in df.columns:
            return col
    for col in df.columns:
        if keyword in col:
            return col
    raise ValueError(f"Cannot find {field_label} column in {file_label}")


def make_interest_column_mapping(area_mapping_path: Path) -> dict[str, str]:
    area_mapping = json.loads(area_mapping_path.read_text(encoding="utf-8"))
    return {
        f"{WANT_PREFIX}{normalize_area_key(en_name)}": zh_name
        for en_name, zh_name in area_mapping.items()
    }


def is_truthy_flag(value: object) -> bool:
    if value is None:
        return False
    normalized = str(value).strip().lower()
    return normalized in {"1", "1.0", "true", "yes"}


def get_interested_area(member: pd.Series, want_col_to_zh: dict[str, str]) -> str:
    areas: list[str] = []
    for col_name in member.index:
        if not col_name.startswith(WANT_PREFIX):
            continue
        if is_truthy_flag(member.get(col_name)):
            zh_name = want_col_to_zh.get(col_name, col_name.removeprefix(WANT_PREFIX))
            areas.append(zh_name)
    return "、".join(areas)


def build_member_block(
    member: pd.Series,
    number: int,
    template: str,
    want_col_to_zh: dict[str, str],
    intro_lookup: dict[str, str],
) -> str:
    email = str(member.get(EMAIL_COL, "")).strip()
    email_key = email.casefold()
    other_contacts = str(member.get(CONTACT_COL, "")).strip()
    if email and other_contacts:
        contact = f"Email：{email}\n其他：{other_contacts}"
    else:
        contact = email or other_contacts

    return template.format(
        number=number,
        nickname=str(member.get(NICKNAME_COL, "")).strip(),
        self_introduction=intro_lookup.get(email_key, ""),
        interested_area=get_interested_area(member, want_col_to_zh),
        contact=contact,
    )


def build_members_string(
    group_df: pd.DataFrame,
    target_index: int,
    template: str,
    want_col_to_zh: dict[str, str],
    intro_lookup: dict[str, str],
) -> str:
    teammates = group_df.loc[group_df.index != target_index]
    blocks: list[str] = []

    for number, (_, teammate) in enumerate(teammates.iterrows(), start=1):
        block = build_member_block(
            teammate, number, template, want_col_to_zh, intro_lookup
        ).strip("\n")
        blocks.append(block)

    # Keep exactly one blank line between members.
    return "\n\n".join(blocks)


def build_intro_lookup(staff_data_path: Path, participants_data_path: Path) -> dict[str, str]:
    staff_df = pd.read_csv(staff_data_path, dtype=str, keep_default_na=False)
    participants_df = pd.read_csv(participants_data_path, dtype=str, keep_default_na=False)

    staff_email_col = find_col_by_candidates_or_keyword(
        staff_df,
        candidates=["聯絡用 email", "電子郵件地址", "Email"],
        keyword="email",
        file_label=str(staff_data_path),
        field_label="staff email",
    )
    staff_intro_col = find_col_by_candidates_or_keyword(
        staff_df,
        candidates=["給對方的自我介紹、想說的話或想學到的內容 (約 15 ~ 50 字)"],
        keyword="自我介紹",
        file_label=str(staff_data_path),
        field_label="staff self introduction",
    )
    participants_email_col = find_col_by_candidates_or_keyword(
        participants_df,
        candidates=["Email", "電子郵件地址", "聯絡用 email"],
        keyword="Email",
        file_label=str(participants_data_path),
        field_label="participants email",
    )
    participants_intro_col = find_col_by_candidates_or_keyword(
        participants_df,
        candidates=["給對方的自我介紹、想說的話或想學到的內容（約15～50字）。"],
        keyword="自我介紹",
        file_label=str(participants_data_path),
        field_label="participants self introduction",
    )

    lookup: dict[str, str] = {}
    for src_df, email_col, intro_col in [
        (participants_df, participants_email_col, participants_intro_col),
        (staff_df, staff_email_col, staff_intro_col),
    ]:
        for _, row in src_df.iterrows():
            email = str(row.get(email_col, "")).strip()
            intro = str(row.get(intro_col, "")).strip()
            if not email:
                continue
            if intro:
                lookup[email.casefold()] = intro

    return lookup


def main() -> None:
    args = parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Input CSV not found: {args.input}")
    if not args.template.exists():
        raise FileNotFoundError(f"Template file not found: {args.template}")
    if not args.staff_data.exists():
        raise FileNotFoundError(f"Staff data CSV not found: {args.staff_data}")
    if not args.participants_data.exists():
        raise FileNotFoundError(f"Participants data CSV not found: {args.participants_data}")
    if not args.area_mapping.exists():
        raise FileNotFoundError(f"Area mapping JSON not found: {args.area_mapping}")

    df = pd.read_csv(args.input, dtype=str, keep_default_na=False)
    required_cols = [GROUP_COL, EMAIL_COL, NICKNAME_COL]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    template = args.template.read_text(encoding="utf-8")
    want_col_to_zh = make_interest_column_mapping(args.area_mapping)
    intro_lookup = build_intro_lookup(args.staff_data, args.participants_data)

    rows: list[dict[str, str]] = []
    for _, group_df in df.groupby(GROUP_COL, sort=False):
        for idx, member in group_df.iterrows():
            members_string = build_members_string(
                group_df=group_df,
                target_index=idx,
                template=template,
                want_col_to_zh=want_col_to_zh,
                intro_lookup=intro_lookup,
            )
            rows.append(
                {
                    "receipt": str(member.get(EMAIL_COL, "")).strip(),
                    "recipient_name": str(member.get(NICKNAME_COL, "")).strip(),
                    "group": str(member.get(GROUP_COL, "")).strip(),
                    "members_string": members_string,
                }
            )

    out_df = pd.DataFrame(
        rows, columns=["receipt", "recipient_name", "group", "members_string"]
    )
    out_df.to_csv(args.output, index=False, encoding="utf-8-sig")

    print(f"Output CSV: {args.output}")
    print(f"Rows: {len(out_df)}")


if __name__ == "__main__":
    main()

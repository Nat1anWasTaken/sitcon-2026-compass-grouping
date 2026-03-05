from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from const import experience_mapping


INPUT_CSV_PATH = Path("merged-result.csv")
TEMPLATE_PATH = Path("members-template.txt")
OUTPUT_CSV_PATH = Path("mail-merge.csv")

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
    return parser.parse_args()


def make_want_column_mapping() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for zh_name, en_name in experience_mapping.items():
        col_name = f"{WANT_PREFIX}{en_name.replace(' ', '_').replace('/', '_')}"
        mapping[col_name] = zh_name
    return mapping


def is_truthy_flag(value: object) -> bool:
    if value is None:
        return False
    normalized = str(value).strip().lower()
    return normalized in {"1", "1.0", "true", "yes"}


def get_interested_area(member: pd.Series, want_col_to_zh: dict[str, str]) -> str:
    areas: list[str] = []
    for col_name, zh_name in want_col_to_zh.items():
        if col_name in member.index and is_truthy_flag(member.get(col_name)):
            areas.append(zh_name)
    return "、".join(areas)


def build_member_block(
    member: pd.Series,
    number: int,
    template: str,
    want_col_to_zh: dict[str, str],
) -> str:
    return template.format(
        number=number,
        nickname=str(member.get(NICKNAME_COL, "")).strip(),
        self_introduction="",
        interested_area=get_interested_area(member, want_col_to_zh),
        email=str(member.get(EMAIL_COL, "")).strip(),
        other_contacts=str(member.get(CONTACT_COL, "")).strip(),
    )


def build_members_string(
    group_df: pd.DataFrame,
    target_index: int,
    template: str,
    want_col_to_zh: dict[str, str],
) -> str:
    teammates = group_df.loc[group_df.index != target_index]
    blocks: list[str] = []

    for number, (_, teammate) in enumerate(teammates.iterrows(), start=1):
        block = build_member_block(teammate, number, template, want_col_to_zh).strip("\n")
        blocks.append(block)

    # Keep exactly one blank line between members.
    return "\n\n".join(blocks)


def main() -> None:
    args = parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Input CSV not found: {args.input}")
    if not args.template.exists():
        raise FileNotFoundError(f"Template file not found: {args.template}")

    df = pd.read_csv(args.input, dtype=str, keep_default_na=False)
    required_cols = [GROUP_COL, EMAIL_COL, NICKNAME_COL]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    template = args.template.read_text(encoding="utf-8")
    want_col_to_zh = make_want_column_mapping()

    rows: list[dict[str, str]] = []
    for _, group_df in df.groupby(GROUP_COL, sort=False):
        for idx, member in group_df.iterrows():
            members_string = build_members_string(
                group_df=group_df,
                target_index=idx,
                template=template,
                want_col_to_zh=want_col_to_zh,
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

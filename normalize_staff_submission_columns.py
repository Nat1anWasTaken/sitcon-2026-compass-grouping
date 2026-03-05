import json
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

INPUT_CSV_PATH = Path("staff-submissions.csv")
OUTPUT_CSV_PATH = Path("staff-submissions.standardized.csv")
STATE_JSON_PATH = Path("staff_standardized_names.json")

MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENROUTER_HTTP_REFERER = os.getenv("OPENROUTER_HTTP_REFERER")
OPENROUTER_X_TITLE = os.getenv("OPENROUTER_X_TITLE")

BATCH_SIZE = 30
MAX_RETRIES = 3
RETRY_SLEEP_SECONDS = 2

IDENTITY_COL = "身分別"
AFFILIATION_COL = (
    "目前所在的單位 ( ex: 學生: 校名/系級 ; 社會人士: 工作單位/部門或職稱類型 )"
)
SOCIAL_CONTACT_COL = "其他可提供給對方的聯絡方式 (至少一種)"

SCHEMA = {
    "name": "normalize_staff_submission_columns",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "id": {"type": "string"},
                        "identity": {"type": "string"},
                        "affiliation": {"type": "string"},
                        "social_contact": {"type": "string"},
                    },
                    "required": ["id", "identity", "affiliation", "social_contact"],
                },
            }
        },
        "required": ["items"],
    },
    "strict": True,
}

SYSTEM_PROMPT = """
你是資料清理助手，任務是標準化三個欄位：
1) 身分別
2) 目前所在的單位（校名/機構/公司/組織與其系級、部門、職稱描述）
3) 其他可提供給對方的聯絡方式（重點：社群平台名稱要統一）

請遵守：
- 只回傳符合 JSON Schema 的資料。
- 若輸入語意與「已知標準名稱」一致，必須重用完全相同的標準字串。
- 同一個機構名稱的不同寫法要統一成同一個標準名稱（例如簡稱/別名統一）。
- 社群平台名稱請標準化，例如：
  - IG、ig、Instagram、insta -> Instagram
  - line、Line -> LINE
  - dc -> Discord
  - tg -> Telegram
  保留帳號、連結、ID 等內容，不要刪除資訊。
- 無法判斷時，保留原意並做最小必要正規化（去除頭尾空白、全形半形一致）。
- 不要輸出多餘欄位，不要省略任何 id。
""".strip()


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def triple_key(identity: str, affiliation: str, social_contact: str) -> str:
    return json.dumps([identity, affiliation, social_contact], ensure_ascii=False)


def append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def default_state() -> dict[str, Any]:
    return {
        "known": {
            "identity": [],
            "affiliation": [],
            "social_contact": [],
        },
        "aliases": {},
    }


def migrate_state_if_needed(state: dict[str, Any]) -> dict[str, Any]:
    if "known" in state and "aliases" in state:
        state["known"].setdefault("identity", [])
        state["known"].setdefault("affiliation", [])
        state["known"].setdefault("social_contact", [])
        return state

    migrated = default_state()
    standardized_names = state.get("standardized_names", {})
    for identity in standardized_names.get("identity", []):
        append_unique(migrated["known"]["identity"], clean_text(identity))
    for affiliation in standardized_names.get("affiliation", []):
        append_unique(migrated["known"]["affiliation"], clean_text(affiliation))
    for social_contact in standardized_names.get("social_contact", []):
        append_unique(migrated["known"]["social_contact"], clean_text(social_contact))

    for item in state.get("triple_aliases", []):
        raw = item.get("raw", {})
        normalized = item.get("standardized", {})
        key = triple_key(
            clean_text(raw.get("identity", "")),
            clean_text(raw.get("affiliation", "")),
            clean_text(raw.get("social_contact", "")),
        )
        migrated["aliases"][key] = {
            "identity": clean_text(normalized.get("identity", "")),
            "affiliation": clean_text(normalized.get("affiliation", "")),
            "social_contact": clean_text(normalized.get("social_contact", "")),
        }

    return migrated


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return default_state()

    state = json.loads(path.read_text(encoding="utf-8"))
    return migrate_state_if_needed(state)


def persist_state(path: Path, state: dict[str, Any]) -> None:
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def build_client() -> OpenAI:
    client_kwargs: dict[str, Any] = {}
    if OPENAI_BASE_URL:
        client_kwargs["base_url"] = OPENAI_BASE_URL

    extra_headers: dict[str, str] = {}
    if OPENROUTER_HTTP_REFERER:
        extra_headers["HTTP-Referer"] = OPENROUTER_HTTP_REFERER
    if OPENROUTER_X_TITLE:
        extra_headers["X-Title"] = OPENROUTER_X_TITLE
    if extra_headers:
        client_kwargs["default_headers"] = extra_headers

    return OpenAI(**client_kwargs)


def call_model(
    client: OpenAI,
    batch: list[dict[str, str]],
    known: dict[str, list[str]],
) -> list[dict[str, str]]:
    request_payload = {
        "known_standardized_names": known,
        "batch": batch,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.responses.create(
                model=MODEL,
                temperature=0,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(request_payload, ensure_ascii=False),
                    },
                ],
                text={"format": {"type": "json_schema", **SCHEMA}},
            )
            payload = json.loads(response.output_text)
            items = payload.get("items")
            if not isinstance(items, list):
                raise ValueError("LLM response has invalid items")
            return items
        except Exception as exc:  # noqa: BLE001
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    "Failed to parse model response after retries"
                ) from exc
            time.sleep(RETRY_SLEEP_SECONDS * attempt)

    return []


def chunked(items: list[dict[str, str]], size: int) -> list[list[dict[str, str]]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def main() -> None:
    if not INPUT_CSV_PATH.exists():
        raise FileNotFoundError(f"Input CSV not found: {INPUT_CSV_PATH}")

    df = pd.read_csv(INPUT_CSV_PATH, dtype=str, keep_default_na=False)
    for col in (IDENTITY_COL, AFFILIATION_COL, SOCIAL_CONTACT_COL):
        if col not in df.columns:
            raise KeyError(f"Missing required column: {col}")

    state = load_state(STATE_JSON_PATH)
    alias_map: dict[str, dict[str, str]] = state["aliases"]

    unique_triples: list[tuple[str, str, str]] = []
    seen = set()
    for _, row in df.iterrows():
        triple = (
            clean_text(row[IDENTITY_COL]),
            clean_text(row[AFFILIATION_COL]),
            clean_text(row[SOCIAL_CONTACT_COL]),
        )
        if triple not in seen:
            seen.add(triple)
            unique_triples.append(triple)

    standardized_by_triple: dict[tuple[str, str, str], dict[str, str]] = {}
    unresolved: list[tuple[str, str, str]] = []
    for raw_triple in unique_triples:
        if not raw_triple[0] and not raw_triple[1] and not raw_triple[2]:
            standardized_by_triple[raw_triple] = {
                "identity": "",
                "affiliation": "",
                "social_contact": "",
            }
            continue

        key = triple_key(*raw_triple)
        if key in alias_map:
            standardized_by_triple[raw_triple] = {
                "identity": clean_text(alias_map[key].get("identity", "")),
                "affiliation": clean_text(alias_map[key].get("affiliation", "")),
                "social_contact": clean_text(alias_map[key].get("social_contact", "")),
            }
        else:
            unresolved.append(raw_triple)

    client = build_client()
    if unresolved:
        unresolved_items: list[dict[str, str]] = []
        id_to_triple: dict[str, tuple[str, str, str]] = {}
        for idx, raw_triple in enumerate(unresolved):
            item_id = str(idx)
            unresolved_items.append(
                {
                    "id": item_id,
                    "identity": raw_triple[0],
                    "affiliation": raw_triple[1],
                    "social_contact": raw_triple[2],
                }
            )
            id_to_triple[item_id] = raw_triple

        all_batches = chunked(unresolved_items, BATCH_SIZE)
        for batch_idx, batch in enumerate(all_batches, start=1):
            print(
                f"Processing batch {batch_idx}/{len(all_batches)} (size={len(batch)}) ..."
            )
            items = call_model(client, batch, state["known"])

            expected_ids = {item["id"] for item in batch}
            result_by_id: dict[str, dict[str, str]] = {}
            for item in items:
                item_id = clean_text(item.get("id", ""))
                if item_id not in expected_ids:
                    continue
                result_by_id[item_id] = {
                    "identity": clean_text(item.get("identity", "")),
                    "affiliation": clean_text(item.get("affiliation", "")),
                    "social_contact": clean_text(item.get("social_contact", "")),
                }

            missing_ids = expected_ids - set(result_by_id.keys())
            if missing_ids:
                raise ValueError(f"LLM response missing ids: {sorted(missing_ids)}")

            for item_id, standardized in result_by_id.items():
                raw_triple = id_to_triple[item_id]

                # Keep raw value if model unexpectedly returns empty.
                if not standardized["identity"]:
                    standardized["identity"] = raw_triple[0]
                if not standardized["affiliation"]:
                    standardized["affiliation"] = raw_triple[1]
                if not standardized["social_contact"]:
                    standardized["social_contact"] = raw_triple[2]

                standardized_by_triple[raw_triple] = standardized
                alias_map[triple_key(*raw_triple)] = standardized

                append_unique(state["known"]["identity"], standardized["identity"])
                append_unique(state["known"]["affiliation"], standardized["affiliation"])
                append_unique(
                    state["known"]["social_contact"], standardized["social_contact"]
                )

    new_identity = []
    new_affiliation = []
    new_social_contact = []
    for i in range(len(df)):
        raw_triple = (
            clean_text(df.at[i, IDENTITY_COL]),
            clean_text(df.at[i, AFFILIATION_COL]),
            clean_text(df.at[i, SOCIAL_CONTACT_COL]),
        )
        standardized = standardized_by_triple.get(
            raw_triple,
            {
                "identity": raw_triple[0],
                "affiliation": raw_triple[1],
                "social_contact": raw_triple[2],
            },
        )
        new_identity.append(standardized["identity"])
        new_affiliation.append(standardized["affiliation"])
        new_social_contact.append(standardized["social_contact"])

    df[IDENTITY_COL] = new_identity
    df[AFFILIATION_COL] = new_affiliation
    df[SOCIAL_CONTACT_COL] = new_social_contact

    df.to_csv(OUTPUT_CSV_PATH, index=False, encoding="utf-8-sig")
    persist_state(STATE_JSON_PATH, state)

    print(f"Processed rows: {len(df)}")
    print(f"Output CSV: {OUTPUT_CSV_PATH}")
    print(f"State JSON: {STATE_JSON_PATH}")
    print(f"Known identities: {len(state['known']['identity'])}")
    print(f"Known affiliations: {len(state['known']['affiliation'])}")
    print(f"Known social contacts: {len(state['known']['social_contact'])}")


if __name__ == "__main__":
    main()

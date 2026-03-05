import json
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

INPUT_CSV_PATH = Path("submissions.csv")
OUTPUT_CSV_PATH = Path("submissions.standardized.csv")
STATE_JSON_PATH = Path("standardized_names.json")

MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENROUTER_HTTP_REFERER = os.getenv("OPENROUTER_HTTP_REFERER")
OPENROUTER_X_TITLE = os.getenv("OPENROUTER_X_TITLE")

BATCH_SIZE = 30
MAX_RETRIES = 3
RETRY_SLEEP_SECONDS = 2

INSTITUTION_COL = "學校 / 單位名稱"
DEPARTMENT_COL = "系所 / 職稱"
LEVEL_COL = "級別 / 非學生請填社會人士"

SCHEMA = {
    "name": "normalize_submission_columns",
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
                        "institution": {"type": "string"},
                        "department_or_title": {"type": "string"},
                        "level_or_social": {"type": "string"},
                    },
                    "required": [
                        "id",
                        "institution",
                        "department_or_title",
                        "level_or_social",
                    ],
                },
            }
        },
        "required": ["items"],
    },
    "strict": True,
}

SYSTEM_PROMPT = """
你是資料清理助手，任務是標準化三個欄位：
1) 學校 / 單位名稱（重點：學校、機構、公司、組織名稱要統一）
2) 系所 / 職稱
3) 級別 / 非學生請填社會人士

請遵守：
- 只回傳符合 JSON Schema 的資料。
- 若輸入語意與「已知標準名稱」一致，必須重用完全相同的標準字串。
- 同一個機構名稱的不同寫法（例如「中山大學」與「國立中山大學」）要統一成同一個標準名稱。
- 名稱盡量用正式完整名稱，避免縮寫與口語別名。
- 不要輸出多餘欄位，不要省略任何 id。
- 無法判斷時，保留原意並做最小必要正規化（去除頭尾空白、全形半形一致）。
""".strip()


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def triple_key(institution: str, department: str, level: str) -> str:
    return json.dumps([institution, department, level], ensure_ascii=False)


def append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def default_state() -> dict[str, Any]:
    return {
        "known": {
            "institution": [],
            "department_or_title": [],
            "level_or_social": [],
        },
        "aliases": {},
    }


def migrate_state_if_needed(state: dict[str, Any]) -> dict[str, Any]:
    if "known" in state and "aliases" in state:
        state["known"].setdefault("institution", [])
        state["known"].setdefault("department_or_title", [])
        state["known"].setdefault("level_or_social", [])
        return state

    migrated = default_state()

    standardized_names = state.get("standardized_names", {})
    for institution in standardized_names.get("institution", []):
        append_unique(migrated["known"]["institution"], clean_text(institution))
    for department in standardized_names.get("department_title", []):
        append_unique(migrated["known"]["department_or_title"], clean_text(department))
    for level in standardized_names.get("level_or_social", []):
        append_unique(migrated["known"]["level_or_social"], clean_text(level))

    for item in state.get("pair_aliases", []):
        raw = item.get("raw", {})
        normalized = item.get("standardized", {})
        key = triple_key(
            "",
            clean_text(raw.get("department_title", "")),
            clean_text(raw.get("level_or_social", "")),
        )
        migrated["aliases"][key] = {
            "institution": "",
            "department_or_title": clean_text(normalized.get("department_title", "")),
            "level_or_social": clean_text(normalized.get("level_or_social", "")),
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
    for col in (INSTITUTION_COL, DEPARTMENT_COL, LEVEL_COL):
        if col not in df.columns:
            raise KeyError(f"Missing required column: {col}")

    state = load_state(STATE_JSON_PATH)
    alias_map: dict[str, dict[str, str]] = state["aliases"]

    unique_triples: list[tuple[str, str, str]] = []
    seen = set()
    for _, row in df.iterrows():
        triple = (
            clean_text(row[INSTITUTION_COL]),
            clean_text(row[DEPARTMENT_COL]),
            clean_text(row[LEVEL_COL]),
        )
        if triple not in seen:
            seen.add(triple)
            unique_triples.append(triple)

    standardized_by_triple: dict[tuple[str, str, str], dict[str, str]] = {}
    unresolved: list[tuple[str, str, str]] = []
    for raw_triple in unique_triples:
        if not raw_triple[0] and not raw_triple[1] and not raw_triple[2]:
            standardized_by_triple[raw_triple] = {
                "institution": "",
                "department_or_title": "",
                "level_or_social": "",
            }
            continue

        key = triple_key(*raw_triple)
        if key in alias_map:
            standardized_by_triple[raw_triple] = {
                "institution": clean_text(alias_map[key].get("institution", "")),
                "department_or_title": clean_text(
                    alias_map[key].get("department_or_title", "")
                ),
                "level_or_social": clean_text(
                    alias_map[key].get("level_or_social", "")
                ),
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
                    "institution": raw_triple[0],
                    "department_or_title": raw_triple[1],
                    "level_or_social": raw_triple[2],
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
                    "institution": clean_text(item.get("institution", "")),
                    "department_or_title": clean_text(
                        item.get("department_or_title", "")
                    ),
                    "level_or_social": clean_text(item.get("level_or_social", "")),
                }

            missing_ids = expected_ids - set(result_by_id.keys())
            if missing_ids:
                raise ValueError(f"LLM response missing ids: {sorted(missing_ids)}")

            for item_id, standardized in result_by_id.items():
                raw_triple = id_to_triple[item_id]

                # Keep raw value if model unexpectedly returns empty.
                if not standardized["institution"]:
                    standardized["institution"] = raw_triple[0]
                if not standardized["department_or_title"]:
                    standardized["department_or_title"] = raw_triple[1]
                if not standardized["level_or_social"]:
                    standardized["level_or_social"] = raw_triple[2]

                standardized_by_triple[raw_triple] = standardized
                alias_map[triple_key(*raw_triple)] = standardized

                append_unique(
                    state["known"]["institution"], standardized["institution"]
                )
                append_unique(
                    state["known"]["department_or_title"],
                    standardized["department_or_title"],
                )
                append_unique(
                    state["known"]["level_or_social"], standardized["level_or_social"]
                )

    new_institution = []
    new_department = []
    new_level = []
    for i in range(len(df)):
        raw_triple = (
            clean_text(df.at[i, INSTITUTION_COL]),
            clean_text(df.at[i, DEPARTMENT_COL]),
            clean_text(df.at[i, LEVEL_COL]),
        )
        standardized = standardized_by_triple.get(
            raw_triple,
            {
                "institution": raw_triple[0],
                "department_or_title": raw_triple[1],
                "level_or_social": raw_triple[2],
            },
        )
        new_institution.append(standardized["institution"])
        new_department.append(standardized["department_or_title"])
        new_level.append(standardized["level_or_social"])

    df[INSTITUTION_COL] = new_institution
    df[DEPARTMENT_COL] = new_department
    df[LEVEL_COL] = new_level

    df.to_csv(OUTPUT_CSV_PATH, index=False, encoding="utf-8-sig")
    persist_state(STATE_JSON_PATH, state)

    print(f"Processed rows: {len(df)}")
    print(f"Output CSV: {OUTPUT_CSV_PATH}")
    print(f"State JSON: {STATE_JSON_PATH}")
    print(f"Known institutions: {len(state['known']['institution'])}")
    print(f"Known departments/titles: {len(state['known']['department_or_title'])}")
    print(f"Known levels/social: {len(state['known']['level_or_social'])}")


if __name__ == "__main__":
    main()

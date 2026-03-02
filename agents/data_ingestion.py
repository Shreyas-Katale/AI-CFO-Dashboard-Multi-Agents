from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from agents.base_agent import BaseAgent
from config import config
from message_bus import AgentOutput


class DataIngestionAgent(BaseAgent):
    name = "data_ingestion"
    model = config.models.get("data_ingestion")  # claude-haiku-4-5-20251001
    tools = [
        {
            "name": "read_csv_file",
            "description": (
                "Read a CSV file and return its column names, first 5 rows as "
                "sample data, and basic statistics (row count, null counts per column)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the CSV file"},
                },
                "required": ["file_path"],
            },
        },
        {
            "name": "read_xlsx_file",
            "description": (
                "Read an Excel file. Returns a dict keyed by sheet name, each containing "
                "column names, first 5 rows, and row count. Reads all sheets."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the .xlsx file"},
                },
                "required": ["file_path"],
            },
        },
        {
            "name": "detect_schema",
            "description": (
                "Analyze column names and sample data to map source columns to the standard "
                "financial schema: date, category, amount, type, account, description. "
                "Returns a mapping dict and any columns that could not be mapped."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "file_path":   {"type": "string", "description": "Path to the file to inspect"},
                    "sheet_name":  {"type": "string", "description": "Sheet name (Excel only); omit for CSV"},
                },
                "required": ["file_path"],
            },
        },
        {
            "name": "clean_and_normalize",
            "description": (
                "Apply all cleaning rules to the file: date normalization, currency stripping, "
                "sign inference, missing-value handling, duplicate flagging, and suspicious-row "
                "flagging. Returns a JSON array of normalized records."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "file_path":     {"type": "string", "description": "Path to the source file"},
                    "column_mapping": {
                        "type": "object",
                        "description": "Map of standard field → source column name",
                    },
                    "sheet_name": {"type": "string", "description": "Sheet name (Excel only)"},
                },
                "required": ["file_path", "column_mapping"],
            },
        },
        {
            "name": "compute_quality_score",
            "description": (
                "Compute a 0–100 quality score for normalized records based on completeness, "
                "consistency, validity, and uniqueness. Returns score + detailed breakdown."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "records": {
                        "type": "array",
                        "description": "Array of normalized record dicts",
                    },
                },
                "required": ["records"],
            },
        },
    ]

    # ------------------------------------------------------------------
    # run()
    # ------------------------------------------------------------------

    async def run(self, input_data: dict[str, Any]) -> AgentOutput:
        file_path = input_data.get("file_path", "")
        sheet_name = input_data.get("sheet_name")
        start = self._log_start(f"file={file_path}")

        messages = [
            {
                "role": "user",
                "content": (
                    f"Ingest the financial data file at: {file_path}\n"
                    + (f"Use sheet: {sheet_name}\n" if sheet_name else "")
                    + "Follow your instructions to read, map, clean, score, and return the data."
                ),
            }
        ]

        try:
            final_text, token_usage = await self._call_api(messages)
            elapsed = self._log_completion(start, token_usage, success=True)

            # Parse JSON from the model's final response
            output_data = self._extract_json(final_text)

            return self._make_output(
                success=True,
                data=output_data,
                token_usage=token_usage,
                processing_time_ms=elapsed,
            )

        except Exception as exc:  # noqa: BLE001
            self.logger.error("DataIngestion failed: %s", exc)
            elapsed = self._log_completion(start, token_usage=None, success=False)  # type: ignore[arg-type]
            return self._make_output(
                success=False,
                errors=[str(exc)],
                processing_time_ms=(elapsed if elapsed else 0.0),
            )

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def read_csv_file(self, file_path: str) -> dict[str, Any]:
        df = pd.read_csv(file_path)
        return {
            "columns":    list(df.columns),
            "row_count":  len(df),
            "sample":     df.head(5).to_dict(orient="records"),
            "null_counts": df.isnull().sum().to_dict(),
            "dtypes":     {col: str(dtype) for col, dtype in df.dtypes.items()},
        }

    def read_xlsx_file(self, file_path: str) -> dict[str, Any]:
        xl = pd.ExcelFile(file_path)
        result: dict[str, Any] = {}
        for sheet in xl.sheet_names:
            df = xl.parse(sheet)
            result[sheet] = {
                "columns":    list(df.columns),
                "row_count":  len(df),
                "sample":     df.head(5).to_dict(orient="records"),
                "null_counts": df.isnull().sum().to_dict(),
            }
        return result

    def detect_schema(
        self,
        file_path: str,
        sheet_name: str | None = None,
    ) -> dict[str, Any]:
        df = self._load_df(file_path, sheet_name)
        cols = [c.lower().strip() for c in df.columns]
        original = list(df.columns)

        _aliases: dict[str, list[str]] = {
            "date":        ["date", "transaction date", "posted date", "txn date",
                            "period", "trans date", "value date"],
            "category":    ["category", "type", "dept", "department", "class",
                            "gl code", "expense type", "tag"],
            "amount":      ["amount", "debit", "credit", "value", "sum", "usd",
                            "total", "net amount"],
            "type":        ["type", "dr/cr", "transaction type", "direction"],
            "account":     ["account", "account name", "cost center", "entity",
                            "source", "bank"],
            "description": ["description", "memo", "notes", "narration",
                            "details", "particulars", "reference"],
        }

        mapping: dict[str, str] = {}
        unmapped: list[str] = []

        for orig, col_lower in zip(original, cols):
            matched = False
            for standard, aliases in _aliases.items():
                if standard not in mapping and any(a in col_lower for a in aliases):
                    mapping[standard] = orig
                    matched = True
                    break
            if not matched:
                unmapped.append(orig)

        return {"column_mapping": mapping, "unmapped_columns": unmapped}

    def clean_and_normalize(
        self,
        file_path: str,
        column_mapping: dict[str, str],
        sheet_name: str | None = None,
    ) -> list[dict[str, Any]]:
        df = self._load_df(file_path, sheet_name)

        # Rename to standard names where mapped
        rename = {v: k for k, v in column_mapping.items() if v in df.columns}
        df = df.rename(columns=rename)

        # Ensure all standard columns exist
        for col in ("date", "category", "amount", "type", "account", "description"):
            if col not in df.columns:
                df[col] = None

        # --- Date parsing ---
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["date"] = df["date"].dt.strftime("%Y-%m-%d").where(df["date"].notna(), other=None)

        # --- Amount: strip currency symbols, handle parentheses ---
        df["amount"] = (
            df["amount"]
            .astype(str)
            .str.replace(r"[\$€£¥,]", "", regex=True)
            .str.replace(r"\((\d+\.?\d*)\)", r"-\1", regex=True)
            .str.strip()
        )
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)

        # --- Infer type from sign if not mapped ---
        if "type" not in column_mapping:
            df["type"] = df["amount"].apply(lambda x: "expense" if x < 0 else "income")
        df["amount"] = df["amount"].abs()

        # --- Fill missing non-critical fields ---
        df["category"]    = df["category"].fillna("Uncategorized").replace("", "Uncategorized")
        df["account"]     = df["account"].fillna("Unknown").replace("", "Unknown")
        df["description"] = df["description"].fillna("").astype(str)

        # --- Flags ---
        dup_mask = df.duplicated(subset=["date", "amount", "description"], keep=False)
        df["duplicate_flag"]  = dup_mask
        df["suspicious_flag"] = (df["amount"] == 0) | (df["amount"] > 1_000_000)

        return df.to_dict(orient="records")

    def compute_quality_score(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        if not records:
            return {
                "score": 0,
                "total_rows": 0,
                "clean_rows": 0,
                "flagged_duplicates": 0,
                "flagged_suspicious": 0,
                "missing_fields": {},
                "warnings": ["Dataset is empty"],
                "errors":   ["No records to score"],
            }

        required = ("date", "category", "amount", "type", "account", "description")
        total = len(records)

        missing: dict[str, int] = {f: 0 for f in required}
        valid_dates = 0
        valid_amounts = 0
        known_categories = 0
        known_accounts = 0
        duplicates = sum(1 for r in records if r.get("duplicate_flag"))
        suspicious = sum(1 for r in records if r.get("suspicious_flag"))

        for rec in records:
            for f in required:
                v = rec.get(f)
                if v is None or str(v).strip() in ("", "nan", "None"):
                    missing[f] += 1

            # Consistency checks
            try:
                pd.to_datetime(rec.get("date"))
                valid_dates += 1
            except Exception:  # noqa: BLE001
                pass

            try:
                amt = float(rec.get("amount", "nan"))
                if amt >= 0:
                    valid_amounts += 1
            except (ValueError, TypeError):
                pass

            if rec.get("category", "Uncategorized") != "Uncategorized":
                known_categories += 1
            if rec.get("account", "Unknown") != "Unknown":
                known_accounts += 1

        total_fields = total * len(required)
        total_missing = sum(missing.values())

        completeness = (1 - total_missing / total_fields) * 100 if total_fields else 0
        consistency  = ((valid_dates + valid_amounts) / (2 * total)) * 100 if total else 0
        validity     = ((known_categories + known_accounts) / (2 * total)) * 100 if total else 0
        uniqueness   = (1 - duplicates / total) * 100 if total else 0

        score = round(
            0.40 * completeness
            + 0.30 * consistency
            + 0.20 * validity
            + 0.10 * uniqueness,
            1,
        )

        warnings = []
        errors: list[str] = []
        if score < 60:
            warnings.append(f"Low quality score: {score}/100")
        if score < 40:
            errors.append(f"Critical quality failure: {score}/100")
        if duplicates:
            warnings.append(f"{duplicates} duplicate row(s) detected")
        if suspicious:
            warnings.append(f"{suspicious} suspicious row(s) flagged")

        return {
            "score":               score,
            "total_rows":          total,
            "clean_rows":          total - duplicates - suspicious,
            "flagged_duplicates":  duplicates,
            "flagged_suspicious":  suspicious,
            "missing_fields":      missing,
            "dimensions": {
                "completeness": round(completeness, 1),
                "consistency":  round(consistency, 1),
                "validity":     round(validity, 1),
                "uniqueness":   round(uniqueness, 1),
            },
            "warnings": warnings,
            "errors":   errors,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_df(file_path: str, sheet_name: str | None = None) -> pd.DataFrame:
        path = Path(file_path)
        if path.suffix.lower() in (".xlsx", ".xls"):
            return pd.read_excel(path, sheet_name=sheet_name or 0)
        return pd.read_csv(path)

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        """Pull the first JSON object or array from the model's response text."""
        import re
        # Look for a JSON block (```json ... ``` or bare {...})
        match = re.search(r"```json\s*([\s\S]+?)\s*```", text)
        if match:
            return json.loads(match.group(1))
        # Try the whole text as JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw_response": text}

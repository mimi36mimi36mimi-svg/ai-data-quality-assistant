from __future__ import annotations

from io import BytesIO
from typing import Any
import re

import pandas as pd


MISSING_TEXT = {"", "na", "n/a", "null", "none", "-", "--"}
EXPECTED_NUMERIC = {
    "quantity", "unit_price", "discount_pct", "amount", "total",
    "sales", "revenue", "cost", "price"
}


def _is_missing(value: Any) -> bool:
    if pd.isna(value):
        return True
    if isinstance(value, str) and value.strip().lower() in MISSING_TEXT:
        return True
    return False


def load_dataset(file) -> pd.DataFrame:
    """Load CSV or Excel without changing the source values."""
    name = getattr(file, "name", "").lower()
    if name.endswith(".csv"):
        df = pd.read_csv(file)
    elif name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(file)
    else:
        raise ValueError("Supported formats are CSV, XLSX, and XLS.")
    # A clean positional index makes the displayed source-row numbers reliable.
    return df.reset_index(drop=True)


def _row_number(position: int) -> int:
    # Row 1 is assumed to contain column headers.
    return position + 2


def _add_issue(rows, position, column, value, issue, severity, confidence, details):
    rows.append({
        "source_row": _row_number(position),
        "column": column,
        "value": str(value),
        "issue": issue,
        "severity": severity,
        "confidence": confidence,
        "details": details,
    })


def check_missing_values(df: pd.DataFrame) -> list[dict]:
    issues = []
    for pos in range(len(df)):
        for col in df.columns:
            value = df.iloc[pos][col]
            if _is_missing(value):
                _add_issue(
                    issues, pos, col, value, "Missing value", "Medium",
                    "High", "Cell is empty or contains a recognized missing-value marker."
                )
    return issues


def check_non_numeric_in_numeric_cols(df: pd.DataFrame) -> list[dict]:
    issues = []
    for col in df.columns:
        col_name = str(col).strip().lower()
        series = df[col]
        # Include known numeric fields even if many entries are malformed.
        looks_numeric = (
            col_name in EXPECTED_NUMERIC
            or any(token in col_name for token in ("price", "amount", "quantity", "discount", "revenue", "sales", "cost"))
        )
        if not looks_numeric:
            non_missing = series[~series.map(_is_missing)]
            if len(non_missing) == 0:
                continue
            converted = pd.to_numeric(non_missing, errors="coerce")
            looks_numeric = converted.notna().mean() >= 0.5
        if not looks_numeric:
            continue

        for pos, value in enumerate(series.tolist()):
            if _is_missing(value):
                continue
            if pd.isna(pd.to_numeric(value, errors="coerce")):
                _add_issue(
                    issues, pos, col, value, "Non-numeric value in numeric-looking column",
                    "Medium", "Medium",
                    "Review the value and confirm whether this column should contain numbers."
                )
    return issues


def check_unusual_values(df: pd.DataFrame) -> list[dict]:
    issues = []
    for col in df.columns:
        name = str(col).strip().lower()
        for pos, value in enumerate(df[col].tolist()):
            if _is_missing(value):
                continue
            number = pd.to_numeric(value, errors="coerce")
            if pd.isna(number):
                continue

            if "discount" in name and not 0 <= float(number) <= 100:
                _add_issue(
                    issues, pos, col, value, "Discount outside expected range (0–100)",
                    "High", "High", "Check whether the discount is recorded as a percentage."
                )
            elif "quantity" in name and float(number) < 0:
                _add_issue(
                    issues, pos, col, value, "Negative quantity",
                    "Review", "Medium",
                    "Could represent a return or correction; confirm against the business rules."
                )
            elif "quantity" in name and float(number) == 0:
                _add_issue(
                    issues, pos, col, value, "Zero quantity",
                    "Low", "Medium", "Confirm whether zero-quantity records are valid."
                )
            elif any(token in name for token in ("price", "amount", "revenue", "sales", "cost")) and float(number) < 0:
                _add_issue(
                    issues, pos, col, value, "Negative monetary value",
                    "High", "Medium", "Check whether this is a refund, credit, or data-entry error."
                )
    return issues


def check_outliers_iqr(df: pd.DataFrame) -> list[dict]:
    issues = []
    for col in df.columns:
        name = str(col).strip().lower()
        if any(token in name for token in ("id", "code", "phone", "zip", "postal")):
            continue
        numeric = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(numeric) < 4 or numeric.nunique() < 3:
            continue
        q1, q3 = numeric.quantile([0.25, 0.75])
        iqr = q3 - q1
        if iqr == 0:
            continue
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        for pos, value in enumerate(df[col].tolist()):
            number = pd.to_numeric(value, errors="coerce")
            if not pd.isna(number) and (number < lower or number > upper):
                _add_issue(
                    issues, pos, col, value, "Potential outlier (IQR)",
                    "Review", "Medium",
                    f"Outside the IQR range ({lower:.2f} to {upper:.2f}); an outlier is not automatically an error."
                )
    return issues


def check_duplicates(df: pd.DataFrame) -> list[dict]:
    issues = []
    # Exact repeated rows: strong signal.
    exact_mask = df.duplicated(keep="first")
    for pos, is_duplicate in enumerate(exact_mask.tolist()):
        if is_duplicate:
            _add_issue(
                issues, pos, "All columns", "—", "Exact duplicate row",
                "High", "High", "This row repeats an earlier row across all columns."
            )

    # Repeated values in a likely record identifier.
    id_cols = [c for c in df.columns if str(c).strip().lower() in {"order_id", "invoice_id", "transaction_id", "record_id"}]
    for col in id_cols:
        normalized = df[col].astype("string").str.strip()
        duplicate_mask = normalized.notna() & normalized.duplicated(keep="first")
        for pos, is_duplicate in enumerate(duplicate_mask.tolist()):
            if is_duplicate:
                _add_issue(
                    issues, pos, col, df.iloc[pos][col], "Repeated record ID",
                    "High", "High", "The identifier appears in an earlier row; verify whether this is allowed."
                )

    # Soft business-key signal only; deliberately low confidence.
    lower_map = {str(c).strip().lower(): c for c in df.columns}
    key_names = ("order_date", "date", "product", "product_name", "sales_rep")
    key_cols = [lower_map[n] for n in key_names if n in lower_map]
    if len(key_cols) >= 2:
        soft_mask = df.duplicated(subset=key_cols, keep="first")
        for pos, is_duplicate in enumerate(soft_mask.tolist()):
            if is_duplicate:
                _add_issue(
                    issues, pos, ", ".join(map(str, key_cols)), "—",
                    "Possible similar transaction", "Review", "Low",
                    "These fields match an earlier row, but this alone does not prove duplication."
                )
    return issues


def run_quality_checks_on_df(df: pd.DataFrame) -> pd.DataFrame:
    all_issues = []
    checks = (
        check_missing_values,
        check_non_numeric_in_numeric_cols,
        check_unusual_values,
        check_outliers_iqr,
        check_duplicates,
    )
    for check in checks:
        all_issues.extend(check(df))
    columns = ["source_row", "column", "value", "issue", "severity", "confidence", "details"]
    report = pd.DataFrame(all_issues, columns=columns)
    if not report.empty:
        report = report.sort_values(
            by=["source_row", "severity", "issue"],
            ascending=[True, True, True],
            kind="stable"
        ).reset_index(drop=True)
    return report

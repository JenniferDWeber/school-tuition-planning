"""
STEP 3 — refuse to publish something broken.

This runs before every commit. If it raises, the workflow stops and the live
site keeps yesterday's good data instead of getting today's bad data.

Add your own checks as you learn what "wrong" looks like for your dataset.
"""
import json
import sys

import pandas as pd

from common import DATA, load_config


def validate():
    cfg = load_config()
    path = DATA / "site_data.csv"

    if not path.exists():
        raise SystemExit("FAIL: data/site_data.csv does not exist")

    df = pd.read_csv(path)
    problems = []

    if df.empty:
        problems.append("the dataset is empty")

    for col in (cfg["label_column"], cfg["value_column"]):
        if col not in df.columns:
            problems.append(f"missing required column: {col}")

    if cfg["label_column"] in df.columns and df[cfg["label_column"]].isna().any():
        problems.append("some rows have no label")

    # Guard against a broken source silently gutting the site.
    meta_path = DATA / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    previous = meta.get("rows")
    if previous and len(df) < previous * 0.5:
        problems.append(
            f"row count fell from {previous} to {len(df)} — "
            "that looks like a broken source, not real change"
        )

    # One row for each of the 50 states and DC, no more, no fewer.
    if len(df) != 51:
        problems.append(f"expected 51 rows (50 states + DC), got {len(df)}")
    if "state" in df.columns and df["state"].duplicated().any():
        problems.append("a state appears more than once")

    # Every state has Catholic schools, so a blank means the survey join broke.
    for col in ("catholic_schools", "catholic_students"):
        if col in df.columns and (df[col].isna() | (df[col] <= 0)).any():
            missing = df.loc[df[col].isna() | (df[col] <= 0), "state"].tolist()
            problems.append(f"no {col} for: {', '.join(missing)}")

    # Neighbors must agree both ways: if A borders B, B borders A.
    if {"abbr", "neighbors"} <= set(df.columns):
        nb = {a: set(str(n).split()) if isinstance(n, str) else set()
              for a, n in zip(df["abbr"], df["neighbors"])}
        lopsided = sorted(f"{a}-{b}" for a in nb for b in nb[a]
                          if a not in nb.get(b, set()))
        if lopsided:
            problems.append(f"neighbor list is one-sided: {', '.join(lopsided)}")

    # NCES published about 1.7 million Catholic school students for 2021-22.
    if "catholic_students" in df.columns:
        total = df["catholic_students"].sum()
        if not 1_000_000 <= total <= 2_500_000:
            problems.append(f"Catholic student total {total:,.0f} is implausible")

    # The IRS list was 30 states in September 2026. Zero, or a sudden drop of
    # more than a handful, means the page changed shape, not that states left.
    if "opted_in" in df.columns:
        opted = int(df["opted_in"].sum())
        if opted == 0:
            problems.append("no participating states were read from the IRS page")
        # transform.py carries the last published count forward for this.
        before = meta.get("previous_states_opted_in")
        if before and opted < before - 5:
            problems.append(
                f"participating states fell from {before} to {opted} — "
                "check the IRS page by hand before publishing"
            )

    if problems:
        print("VALIDATION FAILED:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        raise SystemExit(1)

    print(f"validation passed: {len(df)} rows")
    return df


if __name__ == "__main__":
    validate()

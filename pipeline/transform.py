"""
STEP 2 — turn raw data into exactly what the site needs.

  data/site_data.csv   one row per state (and DC): whether it has opted in to
                       the federal scholarship tax credit, and how many
                       Catholic schools and students it has
  data/meta.json       row count, update date, provenance, and the headline
                       numbers the page shows
"""
import html
import json
import re
from datetime import datetime, timezone

import pandas as pd

from common import DATA, load_config, write_json
from fetch import IRS_HTML, PSS_CSV, RAW

# NCES private school survey: ORIENT == 1 is Roman Catholic.
CATHOLIC = 1


def parse_irs(page, state_names):
    """Return (year, as_of, set of participating states) from the IRS page."""
    heading = re.search(
        r"Participating states for (\d{4})\s*\(as of ([^)]+)\)", page, re.I
    )
    if not heading:
        raise SystemExit(
            "FAIL: the IRS page no longer has a 'Participating states for "
            "<year> (as of <date>)' heading — check the page by hand"
        )
    rest = page[heading.end():]
    table = rest[: rest.find("</table>")] if "</table>" in rest else ""

    # Each state sits in its own table cell or on its own line. Match whole
    # entries so "Virginia" never matches inside "West Virginia".
    entries = re.split(r"<br\s*/?>|</?t[dh][^>]*>|</?p>|</?li>", table, flags=re.I)
    entries = {html.unescape(re.sub(r"<[^>]+>", "", e)).strip() for e in entries}
    found = entries & set(state_names)

    return int(heading.group(1)), heading.group(2).strip(), found


def catholic_by_state():
    pss = pd.read_csv(
        PSS_CSV,
        usecols=["PFNLWT", "PSTABB", "ORIENT", "NUMSTUDS"],
        low_memory=False,
    )
    c = pss[pss["ORIENT"] == CATHOLIC].copy()
    c["students"] = c["PFNLWT"] * c["NUMSTUDS"]
    out = c.groupby("PSTABB").agg(
        catholic_schools=("PFNLWT", "sum"), catholic_students=("students", "sum")
    )
    out["all_private_students"] = (
        (pss["PFNLWT"] * pss["NUMSTUDS"]).groupby(pss["PSTABB"]).sum()
    )
    return out.round().astype(int).reset_index().rename(columns={"PSTABB": "abbr"})


def transform():
    cfg = load_config()
    states = pd.read_csv(RAW)

    year, as_of, participating = parse_irs(
        IRS_HTML.read_text(errors="replace"), states["state"]
    )

    df = states.merge(catholic_by_state(), on="abbr", how="left")
    df["opted_in"] = df["state"].isin(participating)
    df["status"] = df["opted_in"].map({True: "Opted in", False: "Not yet"})

    # Families count by where they live, so a school near a state line can
    # serve students from an opted-in neighbor even if its own state is out.
    df["neighbors"] = df["neighbors"].fillna("")
    in_abbr = set(df.loc[df["opted_in"], "abbr"])
    name_of = dict(zip(df["abbr"], df["state"]))
    df["opted_in_neighbors"] = df["neighbors"].map(
        lambda n: "; ".join(name_of[a] for a in n.split() if a in in_abbr)
    )
    df = df.sort_values(cfg["value_column"], ascending=False)
    df = df[["state", "abbr", "status", "opted_in", "catholic_schools",
             "catholic_students", "all_private_students", "neighbors",
             "opted_in_neighbors"]]

    # Remember the last published count so validation can spot a sudden drop.
    meta_path = DATA / "meta.json"
    old = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    previous = old.get("states_opted_in")

    out = DATA / "site_data.csv"
    df.to_csv(out, index=False)

    total = int(df["catholic_students"].sum())
    in_states = int(df.loc[df["opted_in"], "catholic_students"].sum())
    now = datetime.now(timezone.utc)
    write_json(meta_path, {
        "rows": int(len(df)),
        "updated": now.strftime("%B %d, %Y"),
        "updated_iso": now.isoformat(timespec="seconds"),
        "source_name": cfg["source_name"],
        "source_url": cfg["source_url"],
        "irs_year": year,
        "irs_as_of": as_of,
        "states_opted_in": int(df["opted_in"].sum()),
        "previous_states_opted_in": previous,
        "catholic_students_total": total,
        "catholic_students_opted_in": in_states,
        "catholic_share_opted_in": round(in_states / total * 100) if total else 0,
        "catholic_schools_total": int(df["catholic_schools"].sum()),
        "states_not_in": int((~df["opted_in"]).sum()),
        "catholic_students_not_in": total - in_states,
        "not_in_with_opted_neighbor": int(
            ((~df["opted_in"]) & (df["opted_in_neighbors"] != "")).sum()
        ),
    })

    print(f"wrote {len(df)} rows to data/site_data.csv — "
          f"{int(df['opted_in'].sum())} states opted in (IRS, as of {as_of})")
    return df


if __name__ == "__main__":
    transform()

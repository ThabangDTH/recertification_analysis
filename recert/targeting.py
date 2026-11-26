"""Potential household lists (targeting): the poorest eligible households, ranked by PMT score.

For each council, the households with at least one eligible child are ranked by PMT score (lowest =
poorest) and the first CGP_TARGET / OVCB_TARGET households are listed. Households with the same PMT
score are ordered Ultra-Poor first, then by household ID. Households without a PMT score cannot be
ranked and are left out.

  CGP   - households with a proposed new entrant (an eligible child aged 0-17 not yet in the programme)
  OVC-B - households with an eligible child aged 12-17

Eligible children exclude those turning 18 within the next 12 months and the repeated NISSA records of
the same child. Each list is written for every council and for all councils together, as one bordered
data sheet, from the saved results of the recertification analysis (no re-matching). The household
head's ID number and the number of current members are read from the council's NISSA extract.
"""

from __future__ import annotations

import pickle
import re
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz

from .cleaning import clean_text, parse_dob
from .constants import (
    CACHE_NAME, CBC_FULL, CGP_TARGET, CGP_TARGET_DIR, COMBINED_NAME, DISTRICT_NAMES, EXITED_CLASSIFICATIONS,
    MISSING_TOKENS, OUTCOME_NEW, OVCB_TARGET, OVCB_TARGET_DIR,
)
from .excel_report import force_row_height
from .inputs import locate_inputs

PROGRAMMES = {
    "CGP": dict(target=CGP_TARGET, folder=CGP_TARGET_DIR, file="Potential_CGP_Households"),
    "OVC-B": dict(target=OVCB_TARGET, folder=OVCB_TARGET_DIR, file="Potential_OVCB_Households"),
}
MEMBER_COLS = ["HouseholdId", "HouseholdMember_Status", "System Collection_Household Member Classification",
               "Household Roster_Relationship", "Household Roster_Member First name", "Household Roster_Member Surname",
               "Original_FirstName", "Original_Surname", "Household Roster_Date of Birth", "Original_DateOfBirth",
               "Household Roster_Identification Number", "Original_IdentificationNumber"]


def candidate_pool(R: dict, programme: str) -> pd.DataFrame:
    """Eligible children for a programme, without those turning 18 within the next 12 months.

    CGP: proposed new entrants (eligible, not yet in the programme). OVC-B: eligible children 12-17.
    NISSA sometimes holds the same child several times (same household, name and date of birth, mostly
    new members saved more than once with member ID 0); only one record per child is kept, preferring
    one with a real member ID."""
    pool = R["elig"][R["elig"]["Recert_Status"] == OUTCOME_NEW] if programme == "CGP" else R["ovcb"]
    pool = pool[~pool["Ages_Out_12m"].fillna(False).astype(bool)]
    pool = pool.assign(_no_id=pool["HouseholdMemberId"] == 0).sort_values(["_no_id", "midx"])
    pool = pool.drop_duplicates(["HouseholdId", "FirstName", "Surname", "DOB"]).drop(columns="_no_id")
    return pool.sort_values("midx").copy()


def select_households(pool: pd.DataFrame, target: int) -> pd.DataFrame:
    """The `target` poorest households that have at least one child in `pool`.

    Ranked by PMT score (lowest first); households with the same score are ordered Ultra-Poor before
    Poor, then by household ID, so ties at the cut-off are settled the same way every time. Returns one
    row per household with Household_Rank (1 = poorest) and Eligible_Children."""
    ranked = pool[pool["PMT_Score"].notna()]
    hh = (ranked.groupby("HouseholdId").agg(PMT=("PMT_Score", "first"), CBC=("Updated_CBC", "first"),
                                            Eligible_Children=("HouseholdId", "size")).reset_index())
    hh["Tie_Order"] = (hh["CBC"] != "Ultra-Poor").astype(int)  # Ultra-Poor first among equal PMT scores
    hh = hh.sort_values(["PMT", "Tie_Order", "HouseholdId"]).head(target).reset_index(drop=True)
    hh["Household_Rank"] = range(1, len(hh) + 1)
    return hh


def clean_id(value) -> str:
    """An ID number as text, or '' for placeholders ('9998 NO VALUE', '999999999999') and stray short values."""
    s = str(value).strip()
    s = s[:-2] if s.endswith(".0") else s
    if s.upper() in MISSING_TOKENS or not s.isdigit() or len(s) < 6 or set(s) <= {"0"} or set(s) <= {"9"}:
        return ""
    return s


def read_members(nissa_path: Path) -> pd.DataFrame:
    """Current household members from a NISSA extract, one row per person (repeated records removed).

    Names and date of birth come from the roster, falling back to the original listing; a member counts
    once even if NISSA holds them several times (same household, name and date of birth)."""
    m = pd.read_excel(nissa_path, sheet_name="EnumeratedHouseholdMembers", usecols=lambda c: c in MEMBER_COLS)
    if "HouseholdMember_Status" not in m:  # some extracts omit it: it follows from the member classification
        cls = m["System Collection_Household Member Classification"].astype("string").str.strip().str.lower()
        m["HouseholdMember_Status"] = (~cls.isin(EXITED_CLASSIFICATIONS)).astype(int)
    m = m[m["HouseholdMember_Status"] == 1].copy()
    first = clean_text(m["Household Roster_Member First name"])
    sur = clean_text(m["Household Roster_Member Surname"])
    m["First"] = first.where(first != "", clean_text(m["Original_FirstName"]))
    m["Sur"] = sur.where(sur != "", clean_text(m["Original_Surname"]))
    m["DOB"] = parse_dob(m["Household Roster_Date of Birth"]).fillna(parse_dob(m["Original_DateOfBirth"]))
    return m.drop_duplicates(["HouseholdId", "First", "Sur", "DOB"])


def head_ids(members: pd.DataFrame, heads: pd.Series) -> pd.Series:
    """Household head ID number per household (index HouseholdId), '' when not recorded.

    Uses the roster ID of the current member recorded as Household Head, else their original listing ID.
    Where a household lists more than one current head, the one whose name best matches the household
    head named on the household record (`heads`, indexed by HouseholdId) is used."""
    h = members[members["Household Roster_Relationship"] == "Household Head"].copy()
    roster = h["Household Roster_Identification Number"].map(clean_id)
    h["Head_ID"] = roster.where(roster != "", h["Original_IdentificationNumber"].map(clean_id))
    named = h["HouseholdId"].map(heads).fillna("").astype(str).str.upper()
    h["Score"] = [fuzz.token_sort_ratio(f"{a} {b}", c) for a, b, c in zip(h["First"], h["Sur"], named)]
    best = h.sort_values(["HouseholdId", "Score"], ascending=[True, False]).drop_duplicates("HouseholdId")
    return best.set_index("HouseholdId")["Head_ID"]


def district_name(d) -> str:
    """Proper district name, whatever the extract's spelling ('Mohales Hoek', 'Mohale´S Hoek', ...)."""
    d = "" if pd.isna(d) else str(d)
    return DISTRICT_NAMES.get(re.sub(r"[^a-z]", "", d.lower()), d)


def list_table(sel: pd.DataFrame, R: dict, ids: pd.Series, members: pd.Series) -> pd.DataFrame:
    """The simple list: one row per selected household, poorest first."""
    hh = R["hh"].drop_duplicates("HouseholdId").set_index("HouseholdId")
    h = sel["HouseholdId"]
    return pd.DataFrame({
        "District": h.map(hh["District"].map(district_name)).fillna(""),
        "Community Council": R["council"],
        "Village": h.map(hh["Village"]),
        "Household ID": h,
        "Household Head": h.map(hh["HouseholdHead"]),
        "Household Head ID": h.map(ids).fillna(""),
        "Community Classification": sel["CBC"].map(CBC_FULL),
        "PMT": sel["PMT"].round(2),
        "Number of Members": h.map(members).fillna(0).astype(int),
        "Number of Children": sel["Eligible_Children"],
    })


def write_list(path: Path, table: pd.DataFrame):
    """Write the list as one data sheet: coloured header, borders on every cell, fitted columns, filter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="xlsxwriter") as xw:
        table.to_excel(xw, sheet_name="PotentialHouseholds", index=False)
        wb, ws = xw.book, xw.sheets["PotentialHouseholds"]
        head = wb.add_format({"bold": True, "bg_color": "#184f95", "font_color": "white", "valign": "vcenter",
                              "border": 1, "border_color": "#000000"})
        border = wb.add_format({"border": 1, "border_color": "#000000"})
        for j, c in enumerate(table.columns):
            ws.write(0, j, c, head)
            longest = table[c].dropna().astype(str).str.len().max() if table[c].notna().any() else 0
            ws.set_column(j, j, max(len(c) * 1.1 + 4, longest * 1.1 + 2))
        if len(table):  # borders on every data cell, including empty ones
            ws.conditional_format(1, 0, len(table), len(table.columns) - 1,
                                  {"type": "formula", "criteria": "=TRUE", "format": border})
        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, max(len(table), 1), len(table.columns) - 1)
    force_row_height(path, keep=())


def load_councils(out_root: Path, base: Path) -> list[tuple[dict, dict]]:
    """Each council's saved results with its CGP and OVC-B potential household tables.

    Returns [(R, {"CGP": table, "OVC-B": table}), ...] in council order. Shared by the Excel lists and
    the enrolment invitation forms, so both always hold the same households."""
    out = []
    for c in sorted(p for p in out_root.glob(f"*/{CACHE_NAME}") if p.parent.name != COMBINED_NAME):
        with open(c, "rb") as fh:
            R = pickle.load(fh)
        nissa = locate_inputs(base, R["council"])["nissa"]
        heads = R["hh"].drop_duplicates("HouseholdId").set_index("HouseholdId")["HouseholdHead"]
        if nissa:
            members = read_members(nissa)
            ids, counts = head_ids(members, heads), members.groupby("HouseholdId").size()
        else:
            ids, counts = pd.Series(dtype=str), R["hh"].set_index("HouseholdId")["Active_Members"]
        tables = {prog: list_table(select_households(candidate_pool(R, prog), P["target"]), R, ids, counts)
                  for prog, P in PROGRAMMES.items()}
        out.append((R, tables))
    return out


def build_targeting(out_root: Path, base: Path = Path(".")) -> bool:
    """Write the CGP and OVC-B potential household lists for every council and for all councils."""
    councils = load_councils(out_root, base)
    if not councils:
        print("\n   ! no saved council results found - run the analysis first (--all or --council)")
        return False
    for programme, P in PROGRAMMES.items():
        print(f"\n=== Potential {programme} households (target {P['target']} per council) ===")
        tables = []
        for R, lists in councils:
            t = lists[programme]
            tables.append(t)
            write_list(out_root / P["folder"] / R["council"] / f"{P['file']}_{R['council']}.xlsx", t)
            print(f"   {R['council']:12s} {len(t):4d} households, {t['Number of Children'].sum():4d} eligible children, "
                  f"{t['Number of Members'].sum():5d} members (PMT {t['PMT'].min():.1f} to {t['PMT'].max():.1f}) | "
                  f"head ID for {(t['Household Head ID'] != '').sum()}")
        allc = pd.concat(tables, ignore_index=True)
        write_list(out_root / P["folder"] / COMBINED_NAME / f"{P['file']}_{COMBINED_NAME}.xlsx", allc)
        print(f"   All councils: {len(allc):,} households, {allc['Number of Children'].sum():,} eligible children")
        print(f"   -> {out_root / P['folder']}")
    return True

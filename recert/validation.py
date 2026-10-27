"""Community validation (CV): corrections to the Updated CBC from the CV exports.

The latest submission per household wins; corrections are applied only when the household
ID is found in the council's NISSA extract and the head name agrees."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd
from rapidfuzz import fuzz

from .cleaning import clean_label, normalise_cbc
from .constants import (
    CV_ALREADY, CV_CHANGED, CV_CONFIRMED, CV_DIFFERS, CV_DIR, CV_NAME_DIFF, CV_NAME_MIN, CV_NOT_FOUND,
    CV_REQUIRED, POOR_CLASSES,
)


_CV_CACHE: dict = {}


def council_key(name) -> str:
    """Comparable council name: lower case, without a trailing ' CC'."""
    return re.sub(r"\s+cc$", "", str(name).strip().lower())


def _read_cv_file(f: Path) -> pd.DataFrame:
    """Read a CV export. These exports can carry ~1 million blank formatted rows, so stop at the first long gap."""
    wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
    it = wb.worksheets[0].iter_rows(values_only=True)
    hdr, rows, empty = next(it, None), [], 0
    for r in it:
        if all(v is None or str(v).strip() == "" for v in r):
            empty += 1
            if empty > 200:
                break
            continue
        empty = 0
        rows.append(r)
    wb.close()
    return pd.DataFrame(rows, columns=hdr) if hdr else pd.DataFrame()


def load_cv(base: Path) -> pd.DataFrame:
    """All CV records, one row per (council, household): the latest submission wins.

    Files are read in name order; within a file rows are in submission order (sorted by
    _submission_time when the file has it). Earlier submissions are usually "No Change"
    later corrected to "CBC Changed", so the last one is kept."""
    folder = base / CV_DIR
    if str(folder) in _CV_CACHE:
        return _CV_CACHE[str(folder)]
    frames = []
    for f in sorted(p for p in folder.glob("*.xls*") if not p.name.startswith("~$")) if folder.exists() else []:
        d = _read_cv_file(f)
        miss = [c for c in CV_REQUIRED if c not in d.columns]
        if miss:
            print(f"   ! {f.name}: not a community validation file (missing {miss}) - skipped")
            continue
        if "_submission_time" in d:
            d = d.sort_values("_submission_time", kind="stable")
        frames.append(d.assign(CV_File=f.name))
    if not frames:
        _CV_CACHE[str(folder)] = pd.DataFrame()
        return _CV_CACHE[str(folder)]
    cv = pd.concat(frames, ignore_index=True)
    cv = pd.DataFrame({
        "council_key": cv["Select Community Council"].map(council_key),
        "HouseholdId": pd.to_numeric(cv["Enter Household ID"], errors="coerce"),
        "CV_Head": clean_label(cv["hh_head_name"]) if "hh_head_name" in cv else "",
        "CV_Outcome": clean_label(cv["CV Outcome"]),
        "CV_CBC": normalise_cbc(cv["Select the corrected categorization"]),
        "CV_File": cv["CV_File"],
    }).dropna(subset=["HouseholdId"])
    grp = cv.groupby(["council_key", "HouseholdId"])
    cv["Submissions"] = grp["CV_Outcome"].transform("size")
    cv["Conflicting"] = (grp["CV_Outcome"].transform("nunique") > 1) | (grp["CV_CBC"].transform("nunique") > 1)
    cv = cv.drop_duplicates(["council_key", "HouseholdId"], keep="last").reset_index(drop=True)
    _CV_CACHE[str(folder)] = cv
    return cv


def apply_cv(hh: pd.DataFrame, council: str, base: Path) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """Update hh['Updated_CBC'] from community validation. Returns (hh, CV result table or None)."""
    hh["CBC_Before_CV"] = hh["Updated_CBC"]
    hh["Changed_By_CV"] = False
    cv = load_cv(base)
    sub = cv[cv["council_key"] == council_key(council)] if len(cv) else cv
    if sub.empty:
        return hh, None
    m = sub.merge(hh[["HouseholdId", "Village", "HouseholdHead", "Updated_CBC"]], on="HouseholdId", how="left")
    found = m["Updated_CBC"].notna()
    m["Name_Sim"] = [fuzz.token_sort_ratio(str(a).upper(), str(b).upper()) if f else np.nan
                     for a, b, f in zip(m["CV_Head"], m["HouseholdHead"], found)]
    name_ok = m["Name_Sim"] >= CV_NAME_MIN
    says_changed = m["CV_Outcome"].str.lower().str.startswith("cbc changed")
    same = m["CV_CBC"] == m["Updated_CBC"]
    m["Result"] = np.select(
        [~found, ~name_ok, says_changed & ~same & (m["CV_CBC"] != "Unclassified"), says_changed, same],
        [CV_NOT_FOUND, CV_NAME_DIFF, CV_CHANGED, CV_ALREADY, CV_CONFIRMED], default=CV_DIFFERS)
    m["CBC_Before"] = m["Updated_CBC"]
    m["CBC_After"] = np.where(m["Result"] == CV_CHANGED, m["CV_CBC"], m["Updated_CBC"])
    applied = m[m["Result"] == CV_CHANGED].set_index("HouseholdId")["CV_CBC"]
    hit = hh["HouseholdId"].isin(applied.index)
    hh.loc[hit, "Updated_CBC"] = hh.loc[hit, "HouseholdId"].map(applied)
    hh["Changed_By_CV"] = hit
    hh["Is_Poor"] = hh["Updated_CBC"].isin(POOR_CLASSES)
    was, now = m["CBC_Before"].isin(POOR_CLASSES), m["CBC_After"].isin(POOR_CLASSES)
    m["Effect"] = np.select([~found, was & ~now, ~was & now, was & now], [
        "", "Moved out of Poor/Ultra-Poor", "Moved into Poor/Ultra-Poor", "Still Poor/Ultra-Poor"],
        default="Still not Poor/Ultra-Poor")
    print(f"   community validation: {len(m):,} households, {int(hit.sum()):,} CBC changes applied, "
          f"{int((~found).sum())} not in NISSA, {int((found & ~name_ok).sum())} head-name differences")
    return hh, m.drop(columns=["Updated_CBC"])

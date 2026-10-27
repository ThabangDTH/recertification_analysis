"""Finding and loading a council's input files: NISSA extract, InProgram list, PMT scores and the
baseline (old NISSA) household list."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .cleaning import age_at, clean_label, clean_text, normalise_cbc, normalise_sex, parse_dob, to_age
from .constants import (
    EXITED_CLASSIFICATIONS, HH_COLS, INPROGRAM_DIR, MEM_COLS, NISSA_DIR, OLD_NISSA_DIR, PMT_DIR, PMT_SHEET,
    POOR_CLASSES,
)


def _find(folder: Path, council: str, patterns: list[str]) -> Path | None:
    """Find the workbook for a council in a folder: exact name patterns first, then any file whose name contains the council name."""
    if not folder.exists():
        return None
    files = [f for f in folder.glob("*.xls*") if not f.name.startswith("~$")]
    for pat in patterns:
        for f in files:
            if f.stem.lower() == pat.format(c=council).lower():
                return f
    for f in files:  # fallback: council name anywhere in the file name
        if council.lower() in f.stem.lower():
            return f
    return None


def locate_inputs(base: Path, council: str) -> dict[str, Path | None]:
    """Paths of a council's input files (None when missing).

    'nissa', 'inprogram' and 'pmt' are required; 'baseline' (old NISSA extract) is optional."""
    return {
        "nissa": _find(base / NISSA_DIR, council, ["{c}_Extract", "{c}"]),
        "inprogram": _find(base / INPROGRAM_DIR, council, ["{c}"]),
        "pmt": _find(base / PMT_DIR, council, ["Output_{c}", "{c}"]),
        "baseline": _find(base / OLD_NISSA_DIR, council, ["{c}_Extract", "{c} Extract", "{c}"]),
    }


def known_councils(base: Path) -> list[str]:
    """Every council name that appears in the InProgram or NISSA folders."""
    names = set()
    for f in (base / INPROGRAM_DIR).glob("*.xls*"):
        if not f.name.startswith("~$"):
            names.add(f.stem)
    for f in (base / NISSA_DIR).glob("*.xls*"):
        if not f.name.startswith("~$"):
            names.add(re.sub(r"_?extract$", "", f.stem, flags=re.I))
    return sorted(names)


def _read(path: Path, sheet: str, wanted: list[str]) -> pd.DataFrame:
    """Read selected columns of a sheet, warning about optional columns that are missing and stopping on required ones."""
    header = pd.read_excel(path, sheet_name=sheet, nrows=0).columns
    missing = [c for c in wanted if c not in header]
    required_missing = [c for c in missing if c in ("HouseholdId", "Updated CBC")]
    if required_missing:
        raise SystemExit(f"[{path.name}:{sheet}] required column(s) missing: {required_missing}")
    if missing and missing != ["HouseholdMember_Status"]:
        print(f"   ! {path.name}:{sheet} missing optional column(s): {missing}")
    return pd.read_excel(path, sheet_name=sheet, usecols=[c for c in wanted if c in header])


def load_nissa(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load a council's NISSA extract.

    Returns (households, members): households with the normalised Updated/Original CBC and
    a Poor/Ultra-Poor flag; members with cleaned names, local date of birth, age (roster age,
    else computed from the date of birth) and sex. Roster values are used first, falling back
    to the original listing for members who moved out."""
    hh = _read(path, "EnumeratedHouseholds", HH_COLS)
    mem = _read(path, "EnumeratedHouseholdMembers", MEM_COLS)
    if "HouseholdMember_Status" not in mem:
        # Some extracts omit the status column. It is fully determined by the member classification
        # (checked on 246,584 rows across 8 councils): moved out / passed away / data error = 0, else 1.
        cls = mem["System Collection_Household Member Classification"].astype("string").str.strip().str.lower()
        mem["HouseholdMember_Status"] = (~cls.isin(EXITED_CLASSIFICATIONS)).astype(int)
        print("   ! HouseholdMember_Status column missing - derived from the member classification")
    for c in HH_COLS:
        if c not in hh:
            hh[c] = pd.NA
    for c in MEM_COLS:
        if c not in mem:
            mem[c] = pd.NA

    h = pd.DataFrame({
        "HouseholdId": hh["HouseholdId"],
        "District": clean_label(hh["PackageEvent_OrgUnitName_District"]),
        "Council": clean_label(hh["PackageEvent_OrgUnitName_CC"]),
        "Village": clean_label(hh["System Listing_Village Name"]).where(
            clean_label(hh["System Listing_Village Name"]) != "", clean_label(hh["Original_VillageName"])),
        "HouseholdHead": clean_label(hh["Updated HouseholdHead"]),
        "Updated_CBC_Raw": clean_label(hh["Updated CBC"]),
        "Original_CBC_Raw": clean_label(hh["Original_CommunityClassification"]),
        "CollectionDate": pd.to_datetime(hh["CollectionStatusDate"].astype("string").str.slice(0, 19),
                                         errors="coerce", format="mixed").dt.normalize(),
    })
    h["Updated_CBC"] = normalise_cbc(h["Updated_CBC_Raw"])
    h["Original_CBC"] = normalise_cbc(h["Original_CBC_Raw"])
    h["Is_Poor"] = h["Updated_CBC"].isin(POOR_CLASSES)
    h = h.drop_duplicates("HouseholdId")

    roster_first = clean_text(mem["Household Roster_Member First name"])
    roster_sur = clean_text(mem["Household Roster_Member Surname"])
    roster_dob = parse_dob(mem["Household Roster_Date of Birth"])
    roster_sex = normalise_sex(mem["Household Roster_Sex"])
    m = pd.DataFrame({
        "HouseholdId": mem["HouseholdId"],
        "HouseholdMemberId": mem["HouseholdMemberId"],
        "Status": pd.to_numeric(mem["HouseholdMember_Status"], errors="coerce").fillna(0).astype(int),
        "Classification": clean_label(mem["System Collection_Household Member Classification"]),
        # Roster (updated) values first, falling back to the original listing for moved-out members
        "FirstName": roster_first.where(roster_first != "", clean_text(mem["Original_FirstName"])),
        "OtherNames": clean_text(mem["Household Roster_Member Other names"]),
        "Surname": roster_sur.where(roster_sur != "", clean_text(mem["Original_Surname"])),
        "DOB": roster_dob.fillna(parse_dob(mem["Original_DateOfBirth"])),
        "Age_Roster": to_age(mem["Household Roster_Age in Years"]),
        "Sex": roster_sex.where(roster_sex != "", normalise_sex(mem["Original_Gender"])),
        "Relationship": clean_label(mem["Household Roster_Relationship"]),
    })
    m = m.merge(h[["HouseholdId", "CollectionDate"]], on="HouseholdId", how="left")
    ref = m["CollectionDate"].fillna(pd.Timestamp(date.today()))
    m["Age_From_DOB"] = age_at(m["DOB"], ref)
    m["Age"] = m["Age_Roster"].fillna(m["Age_From_DOB"])
    m["Age_Source"] = np.where(m["Age_Roster"].notna(), "Roster",
                               np.where(m["Age_From_DOB"].notna(), "Computed from DOB", "Unknown"))
    return h, m


def load_pmt(path: Path) -> pd.DataFrame:
    """Load the PMT_Results sheet as (HouseholdId, PMT_Score); the score column name may vary."""
    p = pd.read_excel(path, sheet_name=PMT_SHEET)
    norm = {re.sub(r"[^a-z]", "", c.lower()): c for c in p.columns}
    id_col = norm.get("householdid")
    score_col = norm.get("pmtscore")
    if not id_col or not score_col:
        raise SystemExit(f"[{path.name}:{PMT_SHEET}] could not find Household_Id / PMT Score columns: {list(p.columns)}")
    out = pd.DataFrame({"HouseholdId": p[id_col], "PMT_Score": pd.to_numeric(p[score_col], errors="coerce")})
    dups = out["HouseholdId"].duplicated().sum()
    if dups:
        print(f"   ! {dups} duplicate Household_Id rows in PMT file - keeping the first")
    return out.drop_duplicates("HouseholdId")


def load_inprogram(path: Path) -> pd.DataFrame:
    """Load the current beneficiary list with cleaned names, local date of birth, age and sex."""
    b = pd.read_excel(path)
    need = ["HouseholdId", "FirstName", "LastName", "DateOfBirth", "Age", "Gender"]
    miss = [c for c in need if c not in b.columns]
    if miss:
        raise SystemExit(f"[{path.name}] missing column(s): {miss}")
    out = pd.DataFrame({
        "Prog_HouseholdId": b["HouseholdId"],
        "Prog_MemberId": b["HouseholdMemberId"] if "HouseholdMemberId" in b else range(len(b)),
        "Prog_HouseholdHead": clean_label(b["HouseholdHeadName"]) if "HouseholdHeadName" in b else "",
        "Prog_FirstName": clean_text(b["FirstName"]),
        "Prog_Surname": clean_text(b["LastName"]),
        "Prog_DOB": parse_dob(b["DateOfBirth"]),
        "Prog_Age": to_age(b["Age"]),
        "Prog_Sex": normalise_sex(b["Gender"]),
    })
    out = out.reset_index(drop=True)
    out["bidx"] = out.index
    return out


def load_baseline(path: Path | None) -> pd.DataFrame | None:
    """Load the baseline (old NISSA) household list: one row per household with its baseline CBC.

    The file has one row per household (HouseholdId, Poverty_Status, ...); the few repeated
    household IDs are counted once. 'Do not know' becomes Unclassified. Returns None without a file."""
    if path is None:
        return None
    b = pd.read_excel(path)
    if "HouseholdId" not in b or "Poverty_Status" not in b:
        print(f"   ! {path.name}: baseline file needs HouseholdId and Poverty_Status columns - ignored")
        return None
    b = b.drop_duplicates("HouseholdId")
    return pd.DataFrame({"HouseholdId": b["HouseholdId"].to_numpy(),
                         "Baseline_CBC": normalise_cbc(b["Poverty_Status"]).to_numpy()})

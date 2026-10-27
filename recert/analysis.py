"""The recertification analysis for one council: eligibility, matching and decisions."""

from __future__ import annotations

import time
from datetime import date

import numpy as np
import pandas as pd

from .constants import (
    EXIT_AGED_OUT, EXIT_DATA_ERR, EXIT_DECEASED, EXIT_DUPLICATE, EXIT_MOVED, EXIT_NOT_POOR, FLAG_LOW,
    FLAG_NONE, FLAG_NO_HH, OUTCOME_NEW, OUTCOME_REMAIN, OVCB_MAX_AGE, OVCB_MIN_AGE,
)
from .inputs import load_baseline, load_inprogram, load_nissa, load_pmt
from .matching import match_beneficiaries, match_result
from .validation import apply_cv


def analyse(council: str, paths: dict, min_score: float, review_score: float, min_name: float):
    """Run the full recertification analysis for one council.

    Loads the inputs, applies community validation to the CBC, attaches PMT scores, flags
    CGP-eligible children (0-17), OVC-B-eligible children (12-17) and PA-eligible households
    (no member aged 0-17), matches the beneficiary list to NISSA and decides Remain / Exit /
    Flag / Proposed new entrant for every CGP child and household. Also loads the baseline
    (old NISSA) household list when available. Returns a dict of result frames."""
    t0 = time.time()
    print(f"\n=== {council} ===")
    for k, v in paths.items():
        print(f"   {k:9s}: {v}")

    hh, mem = load_nissa(paths["nissa"])
    hh, cv = apply_cv(hh, council, paths["nissa"].parents[1])  # community validation corrections to the CBC
    pmt = load_pmt(paths["pmt"])
    ben = load_inprogram(paths["inprogram"])
    print(f"   loaded: {len(hh):,} households, {len(mem):,} member rows, {len(pmt):,} PMT rows, "
          f"{len(ben):,} beneficiaries ({time.time() - t0:.1f}s)")

    # ---- PMT ---------------------------------------------------------------------------
    hh = hh.merge(pmt, on="HouseholdId", how="left")
    hh["PMT_Percentile"] = (hh["PMT_Score"].rank(pct=True) * 100).round(1)

    # ---- Eligibility -------------------------------------------------------------------
    mem = mem.merge(hh[["HouseholdId", "Updated_CBC", "Is_Poor", "Village", "HouseholdHead", "PMT_Score"]],
                    on="HouseholdId", how="left")
    mem["Is_Active"] = mem["Status"] == 1
    mem = mem.reset_index(drop=True)
    mem["midx"] = mem.index

    # ---- Matching ----------------------------------------------------------------------
    t1 = time.time()
    final, near, scored, dup = match_beneficiaries(ben, mem, min_score, review_score, min_name)
    print(f"   matching done in {time.time() - t1:.1f}s")

    # A matched child with no age in NISSA takes the age from the programme list
    prog_age = final[["midx", "bidx"]].merge(ben[["bidx", "Prog_Age"]], on="bidx").set_index("midx")["Prog_Age"]
    fill = mem["Age"].isna() & mem["midx"].isin(prog_age.index)
    mem.loc[fill, "Age"] = mem.loc[fill, "midx"].map(prog_age)
    mem.loc[fill & mem["Age"].notna(), "Age_Source"] = "Programme list"

    mem["Is_Child"] = mem["Age"].notna() & (mem["Age"] <= 17)
    mem["CGP_Eligible"] = mem["Is_Active"] & mem["Is_Child"] & mem["Is_Poor"].fillna(False)

    # Turning 18 within 12 months of today (planning flag)
    eighteenth = mem["DOB"] + pd.DateOffset(years=18)
    today = pd.Timestamp(date.today())
    mem["Ages_Out_12m"] = mem["CGP_Eligible"] & eighteenth.notna() & (eighteenth <= today + pd.DateOffset(years=1))

    act = mem[mem["Is_Active"]]
    hh_stats = act.groupby("HouseholdId").agg(Active_Members=("midx", "size"),
                                              Children_0_17=("Is_Child", "sum"),
                                              Eligible_Children=("CGP_Eligible", "sum")).reset_index()
    hh = hh.merge(hh_stats, on="HouseholdId", how="left")
    for c in ["Active_Members", "Children_0_17", "Eligible_Children"]:
        hh[c] = hh[c].fillna(0).astype(int)
    hh["CGP_Eligible_HH"] = hh["Is_Poor"] & (hh["Eligible_Children"] > 0)

    # ---- PA and OVC-B eligibility --------------------------------------------------------
    # OVC-B: CGP-eligible children (current members of Poor/Ultra-Poor households) aged 12-17
    mem["OVCB_Eligible"] = mem["CGP_Eligible"] & (mem["Age"] >= OVCB_MIN_AGE) & (mem["Age"] <= OVCB_MAX_AGE)
    ovcb_per_hh = mem[mem["Is_Active"]].groupby("HouseholdId")["OVCB_Eligible"].sum()
    hh["OVCB_Eligible_Children"] = hh["HouseholdId"].map(ovcb_per_hh).fillna(0).astype(int)
    hh["OVCB_Eligible_HH"] = hh["Is_Poor"] & (hh["OVCB_Eligible_Children"] > 0)
    # PA: Poor/Ultra-Poor households that still have members, none of them aged 0-17
    hh["PA_Eligible_HH"] = hh["Is_Poor"] & (hh["Active_Members"] > 0) & (hh["Children_0_17"] == 0)
    ovcb = mem[mem["OVCB_Eligible"]].copy()

    # ---- Baseline (old NISSA) households -----------------------------------------------------
    baseline = load_baseline(paths.get("baseline"))
    if baseline is not None:
        baseline["Visited"] = baseline["HouseholdId"].isin(hh["HouseholdId"])

    m_cols = ["midx", "HouseholdId", "HouseholdMemberId", "FirstName", "OtherNames", "Surname", "DOB", "Age",
              "Sex", "Status", "Classification", "Updated_CBC", "Is_Poor", "Is_Child", "CGP_Eligible",
              "Village", "HouseholdHead", "PMT_Score"]
    bm = ben.merge(final[["bidx", "midx", "score", "final_score", "s_name", "s_first", "s_surname", "s_phonetic",
                          "s_dob", "s_age", "s_sex", "names_swapped", "surname_differs", "in_anchor"]], on="bidx", how="left")
    bm = bm.merge(mem[m_cols].add_prefix("NISSA_").rename(columns={"NISSA_midx": "midx"}), on="midx", how="left")
    bm["Match_Score"] = bm["final_score"].round(1)
    bm["Matched"] = bm["midx"].notna()
    dup = dup.merge(ben[["bidx", "Prog_MemberId", "Prog_HouseholdId"]].rename(columns={
        "bidx": "dup_of_bidx", "Prog_MemberId": "Duplicate_Of_MemberId", "Prog_HouseholdId": "Duplicate_Of_HouseholdId"}),
        on="dup_of_bidx", how="left")
    bm = bm.merge(dup[["bidx", "Duplicate_Of_MemberId", "Duplicate_Of_HouseholdId", "final_score"]]
                  .rename(columns={"final_score": "Duplicate_Score"}), on="bidx", how="left")

    # near-miss info for unmatched beneficiaries
    near = near.merge(mem[["midx", "HouseholdId", "FirstName", "Surname", "DOB", "Age", "Sex"]], on="midx", how="left",
                      suffixes=("", "_m"))
    bm = bm.merge(near[["bidx", "final_score", "HouseholdId_m" if "HouseholdId_m" in near else "HouseholdId",
                        "FirstName", "Surname", "DOB", "Age", "Sex"]].rename(columns={
        "final_score": "Best_Candidate_Score", "HouseholdId_m": "Best_Candidate_HouseholdId",
        "HouseholdId": "Best_Candidate_HouseholdId", "FirstName": "Best_Candidate_FirstName",
        "Surname": "Best_Candidate_Surname", "DOB": "Best_Candidate_DOB", "Age": "Best_Candidate_Age",
        "Sex": "Best_Candidate_Sex"}), on="bidx", how="left")

    def outcome(r):
        """Decide the outcome for one beneficiary row (remain, an exit reason or a flag)."""
        if not r["Matched"]:
            if pd.notna(r["Duplicate_Of_MemberId"]):
                return EXIT_DUPLICATE
            return FLAG_LOW if pd.notna(r["Best_Candidate_Score"]) else FLAG_NONE
        if r["NISSA_Status"] != 1:
            c = str(r["NISSA_Classification"]).lower()
            if "passed" in c or "dece" in c or "died" in c:
                return EXIT_DECEASED
            if "error" in c:
                return EXIT_DATA_ERR
            return EXIT_MOVED
        if pd.notna(r["NISSA_Age"]) and r["NISSA_Age"] > 17:
            return EXIT_AGED_OUT
        if pd.isna(r["NISSA_Is_Poor"]):  # member's household is not in the household sheet: CBC unknown
            return FLAG_NO_HH
        if not r["NISSA_Is_Poor"]:
            return EXIT_NOT_POOR
        return OUTCOME_REMAIN

    bm["Outcome"] = bm.apply(outcome, axis=1)
    bm["Decision"] = np.select([bm["Outcome"] == OUTCOME_REMAIN, bm["Outcome"].isin([FLAG_LOW, FLAG_NONE, FLAG_NO_HH])],
                               ["Remain", "Flag"], default="Exit")
    score_for_level = bm["Match_Score"].fillna(bm["Duplicate_Score"])
    bm["Match_Result"] = [match_result(sc, min_score, review_score) for sc in score_for_level]
    bm.loc[bm["Outcome"] == FLAG_LOW, "Match_Result"] = "Low Match"
    bm.loc[bm["Outcome"] == FLAG_NONE, "Match_Result"] = "No Match"
    bm["Same_HouseholdId_Both_Systems"] = np.where(
        bm["Matched"], np.where(bm["Prog_HouseholdId"] == bm["NISSA_HouseholdId"], "Yes", "No"), "")


    # ---- Member-level status of NISSA eligible children --------------------------------
    matched_m = bm.loc[bm["Matched"], ["midx", "Prog_HouseholdId", "Prog_MemberId", "Match_Score", "Match_Result"]]
    elig = mem[mem["CGP_Eligible"]].merge(matched_m, on="midx", how="left")
    elig["Recert_Status"] = np.where(elig["Prog_MemberId"].notna(), OUTCOME_REMAIN, OUTCOME_NEW)

    # ---- Household-level -----------------------------------------------------------------
    hh_in_prog = set(bm.loc[bm["Matched"], "NISSA_HouseholdId"])
    hh_remain = set(elig.loc[elig["Recert_Status"] == OUTCOME_REMAIN, "HouseholdId"])

    def hh_status(r):
        """Recertification status of one NISSA household."""
        if r["CGP_Eligible_HH"]:
            return OUTCOME_REMAIN if r["HouseholdId"] in hh_remain else OUTCOME_NEW
        if r["HouseholdId"] in hh_in_prog:
            return "Exit"
        return "Not eligible"

    hh["Matched_To_Program"] = hh["HouseholdId"].isin(hh_in_prog)
    hh["Recert_Status"] = hh.apply(hh_status, axis=1)
    hh["Reason"] = np.select(
        [hh["Recert_Status"] == OUTCOME_REMAIN, hh["Recert_Status"] == OUTCOME_NEW,
         ~hh["Is_Poor"], hh["Eligible_Children"] == 0],
        ["Poor/Ultra-Poor with children 0-17, already in programme",
         "Poor/Ultra-Poor with children 0-17, not in programme",
         "Updated CBC is " + hh["Updated_CBC"], "No active members aged 0-17"], default="")
    hh["CBC_Change"] = np.where(hh["Original_CBC"] == hh["Updated_CBC"], "Unchanged",
                                hh["Original_CBC"] + " -> " + hh["Updated_CBC"])
    prog_ids_by_hh = (bm[bm["Matched"]].groupby("NISSA_HouseholdId")["Prog_HouseholdId"]
                      .agg(lambda s: ", ".join(str(int(x)) for x in sorted(set(s)))))
    hh["Program_HouseholdId(s)"] = hh["HouseholdId"].map(prog_ids_by_hh).fillna("")

    # In-programme household view
    ph = bm.groupby("Prog_HouseholdId").agg(
        Beneficiaries=("bidx", "size"),
        Matched=("Matched", "sum"),
        Remaining=("Decision", lambda s: (s == "Remain").sum()),
        Exiting=("Decision", lambda s: (s == "Exit").sum()),
        Flagged=("Decision", lambda s: (s == "Flag").sum()),
        Avg_Match_Score=("Match_Score", "mean"),
        NISSA_HouseholdIds=("NISSA_HouseholdId",
                            lambda s: ", ".join(str(int(x)) for x in sorted(set(s.dropna())))),
        Main_Exit_Reason=("Outcome", lambda s: s[s != OUTCOME_REMAIN].mode().iat[0] if (s != OUTCOME_REMAIN).any() else ""),
    ).reset_index()
    ph["Household_Decision"] = np.select([ph["Remaining"] > 0, ph["Flagged"] > 0], ["Remain", "Flag"], default="Exit")
    ph["Split_Across_NISSA_HHs"] = ph["NISSA_HouseholdIds"].str.count(",") > 0
    ph["Avg_Match_Score"] = ph["Avg_Match_Score"].round(1)
    first_hh = bm[bm["Matched"]].drop_duplicates("Prog_HouseholdId").set_index("Prog_HouseholdId")
    ph["NISSA_HouseholdHead"] = ph["Prog_HouseholdId"].map(first_hh["NISSA_HouseholdHead"]).fillna("")
    ph["NISSA_Updated_CBC"] = ph["Prog_HouseholdId"].map(first_hh["NISSA_Updated_CBC"]).fillna("")
    ph["NISSA_Village"] = ph["Prog_HouseholdId"].map(first_hh["NISSA_Village"]).fillna("")
    ph["PMT_Score"] = ph["Prog_HouseholdId"].map(first_hh["NISSA_PMT_Score"])

    if cv is not None:
        cv = cv.merge(hh[["HouseholdId", "CGP_Eligible_HH", "Eligible_Children"]], on="HouseholdId", how="left")
    for df in (hh, elig, ovcb, bm, ph) + tuple(x for x in (cv, baseline) if x is not None):  # lets councils be combined
        df.insert(0, "Council_Name", council)
    print(f"   finished {council} in {time.time() - t0:.1f}s")
    return dict(council=council, hh=hh, mem=mem, elig=elig, ovcb=ovcb, bm=bm, ph=ph, scored=scored, cv=cv,
                baseline=baseline,
                params=dict(min_score=min_score, review_score=review_score, min_name=min_name), paths=paths)

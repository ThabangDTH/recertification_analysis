"""Headline figures of an analysis."""

from __future__ import annotations

import re

from .constants import (
    CV_CHANGED, CV_ORDER, DISTRICT_NAMES, EXIT_DUPLICATE, MATCH_LEVELS, OUTCOME_NEW, OUTCOME_ORDER, OUTCOME_REMAIN,
)


def summarise(R: dict) -> dict:
    """Headline figures for a council (or the combined analysis) as a flat dict."""
    hh, mem, elig, bm, ph = R["hh"], R["mem"], R["elig"], R["bm"], R["ph"]
    n_ben = len(bm)
    n_matched = int(bm["Matched"].sum())
    oc = bm["Outcome"].value_counts()
    S = {
        "council": R["council"],
        "district": ", ".join(sorted({DISTRICT_NAMES.get(re.sub(r"[^a-z]", "", d.lower()), d)
                                      for d in hh["District"].dropna().unique() if d})),
        "hh_enumerated": len(hh),
        "hh_poor": int(hh["Is_Poor"].sum()),
        "hh_ultra": int((hh["Updated_CBC"] == "Ultra-Poor").sum()),
        "hh_poor_only": int((hh["Updated_CBC"] == "Poor").sum()),
        "hh_eligible": int(hh["CGP_Eligible_HH"].sum()),
        "hh_eligible_poor": int((hh["CGP_Eligible_HH"] & (hh["Updated_CBC"] == "Poor")).sum()),
        "hh_eligible_ultra": int((hh["CGP_Eligible_HH"] & (hh["Updated_CBC"] == "Ultra-Poor")).sum()),
        "hh_with_pmt": int(hh["PMT_Score"].notna().sum()),
        # PA: Poor/Ultra-Poor households with members but none aged 0-17
        "pa_hh": int(hh["PA_Eligible_HH"].sum()),
        "pa_hh_poor": int((hh["PA_Eligible_HH"] & (hh["Updated_CBC"] == "Poor")).sum()),
        "pa_hh_ultra": int((hh["PA_Eligible_HH"] & (hh["Updated_CBC"] == "Ultra-Poor")).sum()),
        "pa_people": int(hh.loc[hh["PA_Eligible_HH"], "Active_Members"].sum()),
        # OVC-B: children aged 12-17 in Poor/Ultra-Poor households
        "ovcb_children": len(R["ovcb"]),
        "ovcb_boys": int((R["ovcb"]["Sex"] == "Male").sum()),
        "ovcb_girls": int((R["ovcb"]["Sex"] == "Female").sum()),
        "ovcb_hh": int(hh["OVCB_Eligible_HH"].sum()),
        "ovcb_hh_poor": int((hh["OVCB_Eligible_HH"] & (hh["Updated_CBC"] == "Poor")).sum()),
        "ovcb_hh_ultra": int((hh["OVCB_Eligible_HH"] & (hh["Updated_CBC"] == "Ultra-Poor")).sum()),
        # children behind the Poor / Ultra-Poor household counts (for "N Households (N Children)")
        "children_eligible_poor": int(hh.loc[hh["CGP_Eligible_HH"] & (hh["Updated_CBC"] == "Poor"), "Eligible_Children"].sum()),
        "children_eligible_ultra": int(hh.loc[hh["CGP_Eligible_HH"] & (hh["Updated_CBC"] == "Ultra-Poor"), "Eligible_Children"].sum()),
        "ovcb_children_poor": int(hh.loc[hh["OVCB_Eligible_HH"] & (hh["Updated_CBC"] == "Poor"), "OVCB_Eligible_Children"].sum()),
        "ovcb_children_ultra": int(hh.loc[hh["OVCB_Eligible_HH"] & (hh["Updated_CBC"] == "Ultra-Poor"), "OVCB_Eligible_Children"].sum()),
        "members_active": int(mem["Is_Active"].sum()),
        "children_active": int((mem["Is_Active"] & mem["Is_Child"]).sum()),
        "children_eligible": len(elig),
        "children_ages_out_12m": int(mem["Ages_Out_12m"].sum()),
        "ben_children": n_ben,
        "ben_households": len(bm[["Council_Name", "Prog_HouseholdId"]].drop_duplicates()),
        "matched": n_matched,
        "match_rate": n_matched / n_ben if n_ben else 0.0,
        "match_levels": {k: int((bm["Match_Result"] == k).sum()) for k in MATCH_LEVELS},
        "remain_children": int(oc.get(OUTCOME_REMAIN, 0)),
        "exit_children": int((bm["Decision"] == "Exit").sum()),
        "flag_children": int((bm["Decision"] == "Flag").sum()),
        "new_children": int((elig["Recert_Status"] == OUTCOME_NEW).sum()),
        "hh_remain": int((hh["Recert_Status"] == OUTCOME_REMAIN).sum()),
        "hh_new": int((hh["Recert_Status"] == OUTCOME_NEW).sum()),
        "hh_exit_nissa": int((hh["Recert_Status"] == "Exit").sum()),
        "prog_hh_remain": int((ph["Household_Decision"] == "Remain").sum()),
        "prog_hh_exit": int((ph["Household_Decision"] == "Exit").sum()),
        "prog_hh_flag": int((ph["Household_Decision"] == "Flag").sum()),
        "prog_hh_split": int(ph["Split_Across_NISSA_HHs"].sum()),
        "duplicates": int(oc.get(EXIT_DUPLICATE, 0)),
        "same_id_rate": float((bm.loc[bm["Matched"], "Same_HouseholdId_Both_Systems"] == "Yes").mean())
        if n_matched else 0.0,
        "outcomes": {k: int(oc.get(k, 0)) for k in OUTCOME_ORDER if k != OUTCOME_NEW},
        "pmt_median_poor": float(hh.loc[hh["Is_Poor"], "PMT_Score"].median()) if hh["Is_Poor"].any() else None,
    }
    S["outcomes"][OUTCOME_NEW] = S["new_children"]
    base = R.get("baseline")
    if base is not None and len(base):
        S["baseline"] = {
            "hh": len(base),
            "poor": int((base["Baseline_CBC"] == "Poor").sum()),
            "ultra": int((base["Baseline_CBC"] == "Ultra-Poor").sum()),
            "visited": int(base["Visited"].sum()),
            "councils": int(base["Council_Name"].nunique()),
        }
    else:
        S["baseline"] = None
    S["baseline_hh"] = S["baseline"]["hh"] if S["baseline"] else None
    cv = R.get("cv")
    if cv is not None and len(cv):
        res = cv["Result"].value_counts()
        ch = cv[cv["Result"] == CV_CHANGED]
        S["cv"] = {
            "records": len(cv),
            "results": {k: int(res.get(k, 0)) for k in CV_ORDER},
            "into_poor": int((ch["Effect"] == "Moved into Poor/Ultra-Poor").sum()),
            "out_of_poor": int((ch["Effect"] == "Moved out of Poor/Ultra-Poor").sum()),
            "conflicting": int(cv["Conflicting"].sum()),
        }
    else:
        S["cv"] = None
    n_d = len([d for d in S["district"].split(", ") if d])
    S["district_label"] = f"{S['district']} district" + ("s" if n_d > 1 else "") if n_d else ""
    return S

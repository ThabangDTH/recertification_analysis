"""Stakeholder-facing tables shared by the Excel workbook and the HTML dashboard."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .constants import (
    CBC_FULL, CBC_ORDER, CV_ALREADY, CV_CHANGED, CV_CONFIRMED, CV_DIFFERS, CV_NAME_DIFF, CV_NAME_MIN,
    CV_NOT_FOUND, CV_ORDER, EXIT_DUPLICATE, FLAG_LOW, MATCH_LEVELS, MATCH_SUGGESTION, OUTCOME_NEW,
    OUTCOME_REMAIN, PLAIN_EXIT, PLAIN_FLAG, POOR_CLASSES, STATUS_NEW, STATUS_REMAINING,
)
from .formatting import fmt, pct, yes


def build_tables(R: dict, S: dict) -> dict:
    """All stakeholder-facing tables, shared by the Excel workbook and the dashboard."""
    hh, elig, bm = R["hh"], R["elig"], R["bm"]

    # ---- household sheets ---------------------------------------------------------------
    combined = bool(R.get("combined"))
    poor = hh[hh["Is_Poor"]].sort_values(["Council_Name", "Village", "HouseholdId"])
    poor_hh = pd.DataFrame({
        "Household ID": poor["HouseholdId"],
        "Village": poor["Village"],
        "Household Head": poor["HouseholdHead"],
        "Community Classification (Updated CBC)": poor["Updated_CBC"].map(CBC_FULL),
        "Previous Classification (Original CBC)": poor["Original_CBC"].map(CBC_FULL),
        "Changed by Community Validation": poor["Changed_By_CV"].map(yes),
        "PMT Score": poor["PMT_Score"].round(2),
        "Household Members": poor["Active_Members"],
        "Children 0-17": poor["Children_0_17"],
    })

    el = hh[hh["CGP_Eligible_HH"]].sort_values(["Council_Name", "Village", "HouseholdId"])
    eligible_hh = pd.DataFrame({
        "Household ID": el["HouseholdId"],
        "Village": el["Village"],
        "Household Head": el["HouseholdHead"],
        "Community Classification (Updated CBC)": el["Updated_CBC"].map(CBC_FULL),
        "Changed by Community Validation": el["Changed_By_CV"].map(yes),
        "PMT Score": el["PMT_Score"].round(2),
        "Household Members": el["Active_Members"],
        "Eligible Children": el["Eligible_Children"],
        "Status": np.where(el["Recert_Status"] == OUTCOME_REMAIN, STATUS_REMAINING, STATUS_NEW),
    })

    # ---- children (NISSA side) ----------------------------------------------------------------
    e = elig.sort_values(["Council_Name", "Village", "HouseholdId", "Age"], ascending=[True, True, True, False])
    eligible_children = pd.DataFrame({
        "Household ID": e["HouseholdId"],
        "Village": e["Village"],
        "Household Head": e["HouseholdHead"],
        "Community Classification (Updated CBC)": e["Updated_CBC"].map(CBC_FULL),
        "PMT Score": e["PMT_Score"].round(2),
        "Member ID": e["HouseholdMemberId"],
        "First Name": e["FirstName"],
        "Surname": e["Surname"],
        "Date of Birth": e["DOB"],
        "Age": e["Age"].astype("Int64"),
        "Sex": e["Sex"],
        "Relationship to Head": e["Relationship"],
        "Status": np.where(e["Recert_Status"] == OUTCOME_REMAIN, STATUS_REMAINING, STATUS_NEW),
        "Turns 18 Within 12 Months": e["Ages_Out_12m"].map(yes),
    })
    if combined:  # every list starts with the council it belongs to
        poor_hh.insert(0, "Community Council", poor["Council_Name"])
        eligible_hh.insert(0, "Community Council", el["Council_Name"])
        eligible_children.insert(0, "Community Council", e["Council_Name"])
    new_entrants = eligible_children[eligible_children["Status"] == STATUS_NEW].drop(columns="Status")

    # ---- PA: Poor/Ultra-Poor households with no member aged 0-17 ------------------------------
    pa = hh[hh["PA_Eligible_HH"]].sort_values(["Council_Name", "Village", "HouseholdId"])
    pa_hh = pd.DataFrame({
        "Household ID": pa["HouseholdId"],
        "Village": pa["Village"],
        "Household Head": pa["HouseholdHead"],
        "Community Classification (Updated CBC)": pa["Updated_CBC"].map(CBC_FULL),
        "Changed by Community Validation": pa["Changed_By_CV"].map(yes),
        "PMT Score": pa["PMT_Score"].round(2),
        "Household Members": pa["Active_Members"],
    })

    # ---- OVC-B: children aged 12-17 in Poor/Ultra-Poor households -------------------------------
    o = R["ovcb"].sort_values(["Council_Name", "Village", "HouseholdId", "Age"], ascending=[True, True, True, False])
    ovcb_children = pd.DataFrame({
        "Household ID": o["HouseholdId"],
        "Village": o["Village"],
        "Household Head": o["HouseholdHead"],
        "Community Classification (Updated CBC)": o["Updated_CBC"].map(CBC_FULL),
        "PMT Score": o["PMT_Score"].round(2),
        "Member ID": o["HouseholdMemberId"],
        "First Name": o["FirstName"],
        "Surname": o["Surname"],
        "Date of Birth": o["DOB"],
        "Age": o["Age"].astype("Int64"),
        "Sex": o["Sex"],
        "Relationship to Head": o["Relationship"],
        "Turns 18 Within 12 Months": o["Ages_Out_12m"].map(yes),
    })
    if combined:
        pa_hh.insert(0, "Community Council", pa["Council_Name"])
        ovcb_children.insert(0, "Community Council", o["Council_Name"])

    # ---- beneficiaries (programme side) ----------------------------------------------------
    b = bm.sort_values(["Council_Name", "Prog_HouseholdId", "Prog_Age"], ascending=[True, True, False])

    def possible_match(r):
        """Note for a flagged or duplicate child: the duplicate's twin or the closest NISSA record."""
        if r["Outcome"] == EXIT_DUPLICATE and pd.notna(r["Duplicate_Of_MemberId"]):
            return f"Same child as programme member {int(r['Duplicate_Of_MemberId'])}"
        if r["Outcome"] != FLAG_LOW or pd.isna(r.get("Best_Candidate_Score")):
            return ""
        dob = r["Best_Candidate_DOB"].strftime("%Y-%m-%d") if pd.notna(r["Best_Candidate_DOB"]) else "no DOB"
        return (f"{r['Best_Candidate_FirstName']} {r['Best_Candidate_Surname']}, {dob}, "
                f"NISSA household {int(r['Best_Candidate_HouseholdId'])} (score {r['Best_Candidate_Score']:.0f})")

    plain = {**PLAIN_EXIT, **PLAIN_FLAG}
    reason = b["Outcome"].map(lambda o: plain.get(o, ("", ""))[0])
    action = b["Outcome"].map(lambda o: plain.get(o, ("", "Continue payment"))[1])
    nissa_name = (b["NISSA_FirstName"].fillna("") + " " + b["NISSA_Surname"].fillna("")).str.strip()
    base = pd.DataFrame({
        "Programme Household ID": b["Prog_HouseholdId"],
        "Programme Member ID": b["Prog_MemberId"],
        "First Name": b["Prog_FirstName"],
        "Surname": b["Prog_Surname"],
        "Date of Birth": b["Prog_DOB"],
        "Age": b["Prog_Age"].astype("Int64"),
        "Sex": b["Prog_Sex"],
    })
    if combined:
        base.insert(0, "Community Council", b["Council_Name"])
    nissa = pd.DataFrame({
        "NISSA Household ID": b["NISSA_HouseholdId"].astype("Int64"),
        "Name in NISSA": nissa_name,
        "Date of Birth in NISSA": b["NISSA_DOB"],
        "Village": b["NISSA_Village"].fillna(""),
        "Household Head": b["NISSA_HouseholdHead"].fillna(""),
        "Community Classification (Updated CBC)": b["NISSA_Updated_CBC"].map(CBC_FULL).fillna(""),
        "PMT Score": b["NISSA_PMT_Score"].round(2),
        "Match Score (%)": b["Match_Score"].round(0).astype("Int64"),
        "Match Result": b["Match_Result"],
    })
    decision = b["Decision"].map({"Remain": "Remaining", "Exit": "Exiting", "Flag": "Flagged for investigation"})
    note = b.apply(possible_match, axis=1)
    already = pd.concat([base, nissa, pd.DataFrame({"Decision": decision, "Reason": reason, "Action Needed": action,
                                                    "Note": note}, index=b.index)], axis=1)
    remaining = pd.concat([base, nissa], axis=1)[b["Decision"].to_numpy() == "Remain"]
    exiting = pd.concat([base, pd.DataFrame({"Exit Reason": reason, "Action Needed": action}, index=b.index),
                         nissa.drop(columns=["Name in NISSA", "Date of Birth in NISSA"]),
                         pd.DataFrame({"Note": note}, index=b.index)], axis=1)[b["Decision"].to_numpy() == "Exit"]
    flagged = pd.concat([base, pd.DataFrame({"Match Result": b["Match_Result"], "Reason": reason,
                                             "Action Needed": action, "Closest NISSA Record": note}, index=b.index)],
                        axis=1)[b["Decision"].to_numpy() == "Flag"]

    # ---- summary tables ----------------------------------------------------------------------
    n_hh, n_ben = S["hh_enumerated"], S["ben_children"]
    cols = ["Measure", "Number", "Note"]
    b = S["baseline"]
    where = "across all councils" if combined else "in the council"
    def hh_(h, c=None, unit="Children"):
        """At-a-glance number: 'N Households', or 'N Households (N Children)' when children are counted too."""
        return f"{fmt(h)} Households" + (f" ({fmt(c)} {unit})" if c is not None else "")

    def n_(x, unit):
        """At-a-glance number for a single count, e.g. '53,908 Children'."""
        return f"{fmt(x)} {unit}"

    hh_glance = pd.DataFrame((
        [("Baseline households (old NISSA data)", hh_(b["hh"]), "Households on the baseline list before the NISSA updating"
          + ("" if not combined or b["councils"] == len(R["council_summaries"])
             else f" ({b['councils']} councils with a baseline file)")),
         ("Baseline Poor households", hh_(b["poor"]), f"{pct(b['poor'], b['hh'])} of baseline households"),
         ("Baseline Ultra-Poor households", hh_(b["ultra"]), f"{pct(b['ultra'], b['hh'])} of baseline households")]
        if b else [])
        + [("Households visited (updated NISSA data)", hh_(S["hh_enumerated"]), f"All households enumerated {where}"
            + (f" - {pct(S['hh_enumerated'], b['hh'])} of the baseline number" if b else ""))]
        + [("Poor households", hh_(S["hh_poor_only"]), f"{pct(S['hh_poor_only'], n_hh)} of households visited"),
           ("Ultra-Poor households", hh_(S["hh_ultra"]), f"{pct(S['hh_ultra'], n_hh)} of households visited")]
        + ([("Households whose CBC was changed by community validation", hh_(S["cv"]["results"][CV_CHANGED]),
             f"{fmt(S['cv']['into_poor'])} moved into and {fmt(S['cv']['out_of_poor'])} out of Poor/Ultra-Poor")]
           if S["cv"] else []), columns=cols)
    cgp_glance = pd.DataFrame([
        ("Eligible Poor households", hh_(S["hh_eligible_poor"], S["children_eligible_poor"]),
         "Poor, with at least one child aged 0-17"),
        ("Eligible Ultra-Poor households", hh_(S["hh_eligible_ultra"], S["children_eligible_ultra"]),
         "Ultra-Poor, with at least one child aged 0-17"),
        ("Eligible households (total)", hh_(S["hh_eligible"], S["children_eligible"]),
         "Poor or Ultra-Poor with at least one child aged 0-17"),
        ("Eligible children", n_(S["children_eligible"], "Children"), "Children aged 0-17 in eligible households"),
        ("Children already in programme", hh_(S["ben_households"], S["ben_children"]), "Current CGP beneficiaries"),
        ("Found in NISSA (match rate)", n_(S["matched"], "Children"), f"{pct(S['matched'], n_ben)} of children already in programme"),
        ("Remaining in programme", hh_(S["prog_hh_remain"], S["remain_children"]), "Still eligible"),
        ("Exiting programme", hh_(S["prog_hh_exit"], S["exit_children"]), "No longer eligible - see the ExitingProgram sheet"),
        ("Flagged for investigation", hh_(S["prog_hh_flag"], S["flag_children"]), "Need checking before any decision - not exited"),
        ("Proposed new entrants", hh_(S["hh_new"], S["new_children"]), "Eligible, not yet in the programme"),
        ("Eligible children turning 18 within 12 months", n_(S["children_ages_out_12m"], "Children"), "Plan for their exit"),
    ], columns=cols)
    pa_glance = pd.DataFrame([
        ("Eligible Poor households", hh_(S["pa_hh_poor"]), "Poor, with no member aged 0-17"),
        ("Eligible Ultra-Poor households", hh_(S["pa_hh_ultra"]), "Ultra-Poor, with no member aged 0-17"),
        ("Eligible households (total)", hh_(S["pa_hh"]), "Poor or Ultra-Poor households with no member aged 0-17"),
        ("People in eligible households", n_(S["pa_people"], "People"), "Current members of the eligible households"),
    ], columns=cols)
    ovcb_glance = pd.DataFrame([
        ("Eligible Poor households", hh_(S["ovcb_hh_poor"], S["ovcb_children_poor"]), "Poor, with at least one child aged 12-17"),
        ("Eligible Ultra-Poor households", hh_(S["ovcb_hh_ultra"], S["ovcb_children_ultra"]),
         "Ultra-Poor, with at least one child aged 12-17"),
        ("Eligible households (total)", hh_(S["ovcb_hh"], S["ovcb_children"]), "Poor or Ultra-Poor with at least one child aged 12-17"),
        ("Eligible children", n_(S["ovcb_children"], "Children"),
         f"Children aged 12-17 in eligible households ({fmt(S['ovcb_boys'])} boys, {fmt(S['ovcb_girls'])} girls)"),
    ], columns=cols)

    cbc_counts = hh["Updated_CBC"].value_counts()
    cbc_rows = [(CBC_FULL[c], int(cbc_counts.get(c, 0)), pct(cbc_counts.get(c, 0), n_hh),
                 "Yes" if c in POOR_CLASSES else "No") for c in CBC_ORDER]
    if cbc_counts.get("Unclassified", 0):
        cbc_rows.append(("Unclassified", int(cbc_counts["Unclassified"]), pct(cbc_counts["Unclassified"], n_hh), "No"))
    by_cbc = pd.DataFrame(cbc_rows, columns=["Community Classification", "Households", "Share", "Eligible?"])

    outcome = pd.DataFrame([
        ("Remaining in programme", S["remain_children"], pct(S["remain_children"], n_ben), S["prog_hh_remain"]),
        ("Exiting programme", S["exit_children"], pct(S["exit_children"], n_ben), S["prog_hh_exit"]),
        ("Flagged for investigation", S["flag_children"], pct(S["flag_children"], n_ben), S["prog_hh_flag"]),
    ], columns=["Children already in programme", "Children", "Share", "Households"])

    oc = bm["Outcome"].value_counts()
    exit_rows = sorted(((PLAIN_EXIT[k][0], int(oc[k]), pct(oc[k], S["exit_children"]), PLAIN_EXIT[k][1])
                        for k in PLAIN_EXIT if oc.get(k, 0)), key=lambda r: -r[1])
    exit_reasons = pd.DataFrame(exit_rows, columns=["Exit Reason", "Children", "Share of Exits", "Action Needed"])

    lv = S["match_levels"]
    match_quality = pd.DataFrame([(f"{k} - {MATCH_SUGGESTION[k]}", lv[k], pct(lv[k], n_ben)) for k in MATCH_LEVELS],
                                 columns=["Match Result", "Children", "Share"])

    villages = by_council = None
    if combined:
        by_council = pd.DataFrame([{
            "Community Council": c["council"],
            "Baseline Households": c["baseline_hh"] if c["baseline_hh"] is not None else "",
            "Households Visited": c["hh_enumerated"],
            "Poor Households": c["hh_poor_only"],
            "Ultra-Poor Households": c["hh_ultra"],
            "Eligible Households": c["hh_eligible"],
            "Eligible Children": c["children_eligible"],
            "Already in Programme": c["ben_children"],
            "Match Rate": f"{100 * c['match_rate']:.1f}%",
            "Remaining": c["remain_children"],
            "Exiting": c["exit_children"],
            "Flagged": c["flag_children"],
            "Proposed New Entrants": c["new_children"],
            "PA Eligible Households": c["pa_hh"],
            "OVC-B Eligible Children": c["ovcb_children"],
        } for c in R["council_summaries"]])
    else:
        vt = hh.groupby("Village").agg(**{
            "Poor/Ultra-Poor Households": ("Is_Poor", "sum"),
            "Eligible Households": ("CGP_Eligible_HH", "sum")}).reset_index()
        ve = elig.groupby("Village").agg(**{
            "Eligible Children": ("midx", "size"),
            "Remaining": ("Recert_Status", lambda s: int((s == OUTCOME_REMAIN).sum())),
            "Proposed New Entrants": ("Recert_Status", lambda s: int((s == OUTCOME_NEW).sum()))}).reset_index()
        vx = (bm[bm["Matched"] & (bm["Decision"] == "Exit")].groupby("NISSA_Village").size()
              .rename("Exiting").reset_index().rename(columns={"NISSA_Village": "Village"}))
        villages = vt.merge(ve, on="Village", how="left").merge(vx, on="Village", how="left").fillna(0)
        for c in villages.columns[1:]:
            villages[c] = villages[c].astype(int)
        villages = villages.sort_values("Eligible Children", ascending=False)

    cv_sheet = cv_summary = cv_changes = None
    cv = R.get("cv")
    if S["cv"]:
        c = cv.assign(_o=cv["Result"].map({k: i for i, k in enumerate(CV_ORDER)})).sort_values(
            ["_o", "Council_Name", "Village", "HouseholdId"])
        cv_sheet = pd.DataFrame({
            "Household ID": c["HouseholdId"].astype("Int64"),
            "Village": c["Village"].fillna(""),
            "Household Head (NISSA)": c["HouseholdHead"].fillna(""),
            "Household Head (Community Validation)": c["CV_Head"],
            "Head Name Check": np.where(c["Name_Sim"].isna(), "", np.where(c["Name_Sim"] >= CV_NAME_MIN, "Agrees", "Differs")),
            "CBC Before Validation": c["CBC_Before"].map(CBC_FULL).fillna(""),
            "CV Outcome": c["CV_Outcome"],
            "Corrected CBC (Community Validation)": c["CV_CBC"].map(CBC_FULL),
            "CBC After Validation": c["CBC_After"].map(CBC_FULL).fillna(""),
            "Result": c["Result"],
            "Effect": c["Effect"],
            "CGP Eligible Household (after validation)": c["CGP_Eligible_HH"].map({True: "Yes", False: "No"}).fillna(""),
            "Eligible Children": c["Eligible_Children"].astype("Int64"),
            "Note": np.where(c["Conflicting"], "Submitted " + c["Submissions"].astype(str)
                             + " times with different answers - latest used", ""),
        })
        if combined:
            cv_sheet.insert(0, "Community Council", c["Council_Name"])
        r = S["cv"]["results"]
        rows = [("Households validated by the community", S["cv"]["records"]),
                ("CBC changed by community validation", r[CV_CHANGED]),
                ("   moved into Poor/Ultra-Poor", S["cv"]["into_poor"]),
                ("   moved out of Poor/Ultra-Poor", S["cv"]["out_of_poor"]),
                ("   changed within the same group", r[CV_CHANGED] - S["cv"]["into_poor"] - S["cv"]["out_of_poor"]),
                ("CBC confirmed - no change", r[CV_CONFIRMED]),
                (CV_ALREADY, r[CV_ALREADY]), (CV_DIFFERS, r[CV_DIFFERS]),
                (CV_NOT_FOUND, r[CV_NOT_FOUND]), (CV_NAME_DIFF, r[CV_NAME_DIFF]),
                ("Submitted more than once with different answers (latest used)", S["cv"]["conflicting"])]
        keep = {"Households validated by the community", "CBC changed by community validation", "CBC confirmed - no change"}
        cv_summary = pd.DataFrame([x for x in rows if x[1] or x[0] in keep], columns=["Community Validation", "Households"])
        ch = cv[cv["Result"] == CV_CHANGED]
        cv_changes = (ch.groupby(["CBC_Before", "CBC_After"]).size().rename("Households").reset_index()
                      .sort_values("Households", ascending=False))
        cv_changes = pd.DataFrame({
            "CBC Change": cv_changes["CBC_Before"].map(lambda x: CBC_FULL[x].split(" (")[0]) + " → "
                          + cv_changes["CBC_After"].map(lambda x: CBC_FULL[x].split(" (")[0]),
            "Households": cv_changes["Households"]})

    return dict(cv_sheet=cv_sheet, cv_summary=cv_summary, cv_changes=cv_changes,
                poor_hh=poor_hh, eligible_hh=eligible_hh, eligible_children=eligible_children,
                already=already, remaining=remaining, exiting=exiting, flagged=flagged, new_entrants=new_entrants,
                pa_hh=pa_hh, ovcb_children=ovcb_children,
                hh_glance=hh_glance, cgp_glance=cgp_glance, pa_glance=pa_glance, ovcb_glance=ovcb_glance,
                by_cbc=by_cbc, outcome=outcome, exit_reasons=exit_reasons,
                match_quality=match_quality, villages=villages, by_council=by_council)

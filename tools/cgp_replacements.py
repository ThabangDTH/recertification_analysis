"""CGP replacement households: replace households on the 400-household Potential CGP lists that are
already in CGP with the next poorest households that are not in the programme.

Same rule as recert/targeting.py: households with a proposed new entrant (eligible child 0-17 not yet in
CGP, not turning 18 within 12 months, repeated NISSA records removed), ranked by PMT score (lowest
first), Ultra-Poor before Poor at the same score, then household ID. Extra rule for the replacements:
the household itself is not already in CGP (household status "Remaining in programme") and is not
already on the original list.

usage: python replacements.py <repo> <Recertification_All_Councils.xlsx> <Potential_CGP_Households dir> <out dir> [--check]
"""
import sys
from pathlib import Path

repo, recert_xlsx, lists_dir, out_dir = map(Path, sys.argv[1:5])
CHECK = "--check" in sys.argv
sys.path.insert(0, str(repo))

import pandas as pd
from recert.constants import CBC_FULL
from recert.inputs import locate_inputs
from recert.targeting import read_members, head_ids, write_list, district_name

REMAIN, NEW = "Remaining in programme", "Proposed new entrant"
CBC_SHORT = {v: k for k, v in CBC_FULL.items()}

ch = pd.read_excel(recert_xlsx, sheet_name="EligibleChildren")
hhs = pd.read_excel(recert_xlsx, sheet_name="EligibleHouseholds")
hh_status = hhs.drop_duplicates("Household ID").set_index("Household ID")["Status"]

# turning 18 within 12 months of the run date (as in recert/analysis.py), recomputed from the date of birth
REF = pd.Timestamp(next((x.split("=")[1] for x in sys.argv if x.startswith("--ref=")), pd.Timestamp.today().date()))
ages_out = pd.to_datetime(ch["Date of Birth"]) + pd.DateOffset(years=18) <= REF + pd.DateOffset(years=1)
pool = ch[(ch["Status"] == NEW) & ~ages_out].copy()
pool["_no_id"] = pool["Member ID"].fillna(0) == 0
pool = pool.sort_values("_no_id", kind="stable").drop_duplicates(
    ["Household ID", "First Name", "Surname", "Date of Birth"])
pool = pool[pool["PMT Score"].notna()]
cand = (pool.groupby(["Community Council", "Household ID"])
        .agg(PMT=("PMT Score", "first"), CBC=("Community Classification (Updated CBC)", "first"),
             Village=("Village", "first"), Head=("Household Head", "first"),
             Eligible_Children=("Household ID", "size")).reset_index())
cand["Tie"] = (~cand["CBC"].astype(str).str.startswith("Ultra")).astype(int)
cand["HH_Status"] = cand["Household ID"].map(hh_status)
cand = cand.sort_values(["Community Council", "PMT", "Tie", "Household ID"])

summary, all_rep = [], []
for council, c in cand.groupby("Community Council", sort=True):
    orig = pd.read_excel(lists_dir / council / f"Potential_CGP_Households_{council}.xlsx")
    if CHECK:  # the original rule must give back the original list
        a=c.head(len(orig)); A=list(a["Household ID"]); B=list(orig["Household ID"])
        print(f"{council:12s} same order {A==B}, same set {set(A)==set(B)}")
        if set(A)!=set(B):
            print(c[c["Household ID"].isin(set(A)^set(B))].to_string()); print('orig max PMT', orig["PMT"].max())
        continue
    on_list = set(orig["Household ID"])
    already = orig[orig["Household ID"].map(hh_status) == REMAIN]
    n = len(already)
    rep = c[(c["HH_Status"] != REMAIN) & ~c["Household ID"].isin(on_list)].head(n).reset_index(drop=True)
    assert len(rep) == n, (council, len(rep), n)

    nissa = locate_inputs(repo, council)["nissa"]
    members = read_members(nissa)
    heads = rep.set_index("Household ID")["Head"]
    ids, counts = head_ids(members, heads), members.groupby("HouseholdId").size()
    h = rep["Household ID"]
    table = pd.DataFrame({
        "District": orig["District"].iat[0],  # one district per council
        "Community Council": council,
        "Village": rep["Village"],
        "Household ID": h,
        "Household Head": rep["Head"],
        "Household Head ID": h.map(ids).fillna(""),
        "Community Classification": rep["CBC"],
        "PMT": rep["PMT"].round(2),
        "Number of Members": h.map(counts).fillna(0).astype(int),
        "Number of Children": rep["Eligible_Children"],
    })
    write_list(out_dir / council / f"Potential_CGP_Households_{council}_Replacements.xlsx", table)
    all_rep.append(table)
    summary.append(dict(District=table["District"].iat[0], Council=council, Original=len(orig), Already_in_CGP=n,
                        Replacements=len(table), Children=int(table["Number of Children"].sum()),
                        PMT_from=table["PMT"].min(), PMT_to=table["PMT"].max(),
                        Last_PMT_original=orig["PMT"].max(),
                        Head_ID=int((table["Household Head ID"] != "").sum())))
if not CHECK:
    allc = pd.concat(all_rep, ignore_index=True)
    write_list(out_dir / "All_Councils" / "Potential_CGP_Households_All_Councils_Replacements.xlsx", allc)
    s = pd.DataFrame(summary)
    print(s.to_string(index=False))
    print("total replacements", len(allc), "children", allc["Number of Children"].sum())

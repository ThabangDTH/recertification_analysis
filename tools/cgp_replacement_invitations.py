"""Enrolment invitation forms (Form B2) for the CGP replacement households, one per council.

Same template and layout as recert/enrolment.py (a new page per village, 8 households per page).
CGP is ticked for every household; OVC is also ticked when the household is on the council's
Potential OVC-B list.

usage: python replacement_invitations.py <repo> <replacements dir> <Potential_OVC-B_Households dir> <out dir>
"""
import sys
import zipfile
from datetime import date
from pathlib import Path

repo, rep_dir, ovcb_dir, out_dir = map(Path, sys.argv[1:5])
sys.path.insert(0, str(repo))

import pandas as pd
from recert.constants import ENROLMENT_ROWS_PER_PAGE, ENROLMENT_TEMPLATE
from recert.enrolment import load_template, page_xml, village_eas, to_pdf
from recert.inputs import locate_inputs

T = load_template(repo / ENROLMENT_TEMPLATE)
today = date.today().strftime("%d/%m/%Y")
word_dir = out_dir / "Word"
word_dir.mkdir(parents=True, exist_ok=True)
written = []
for f in sorted(rep_dir.glob("*/Potential_CGP_Households_*_Replacements.xlsx")):
    council = f.parent.name
    if council == "All_Councils":
        continue
    hh = pd.read_excel(f, dtype={"Household Head ID": str}).fillna({"Household Head ID": ""})
    ovcb = pd.read_excel(next((ovcb_dir / council).glob("Potential_OVC-B_Households_*.xlsx")))
    hh["CGP"] = True
    hh["OVC"] = hh["Household ID"].isin(set(ovcb["Household ID"]))
    hh = hh.sort_values(["Village", "PMT", "Household ID"])
    nissa = locate_inputs(repo, council)["nissa"]
    eas = village_eas(nissa) if nissa else {}
    pages, k = [], 0
    for village, g in hh.groupby("Village", sort=True):
        recs = g.to_dict("records")
        loc = dict(District=g["District"].iat[0], Council=council, Village=village, EA=eas.get(village, ""), Date=today)
        for start in range(0, len(recs), ENROLMENT_ROWS_PER_PAGE):
            pages.append(page_xml(T, k, loc, recs[start:start + ENROLMENT_ROWS_PER_PAGE], start + 1))
            k += 1
    doc = T["head"] + "".join(pages) + T["after"]
    path = word_dir / f"Enrolment_Invitation_List_{council}_Replacements.docx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, data in T["files"].items():
            z.writestr(n, doc.encode("utf-8") if n == "word/document.xml" else data)
    written.append(path)
    print(f"{council:12s} {hh['Village'].nunique():4d} villages, {len(hh):4d} households (also OVC-B {int(hh['OVC'].sum())}), {k} pages")
to_pdf(written)
for p in written:
    target = out_dir / p.with_suffix(".pdf").name
    target.unlink(missing_ok=True)
    p.with_suffix(".pdf").rename(target)
print("->", out_dir)

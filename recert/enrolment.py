"""Enrolment invitation forms (Call for Enrollment List, Form B2) for the potential households.

One document per council, built from the "Enrolment Invitation List.docx" template: every village
starts on a new page with the template's header, logo and location block filled in (District,
Community Council, Village and its EA codes), followed by its households (sequence number, household
ID, head name, head ID). The template holds 8 households per page, so a larger village continues on
further copies of the page with the sequence numbers carrying on. The "Eligible For" boxes are ticked
for CGP and/or OVC; the OAP and PA boxes are removed. Each document is saved as .docx and converted
to PDF with Microsoft Word.

The households are the CGP and OVC-B potential household lists (see targeting.py); a household on
both lists appears once with both boxes ticked.
"""

from __future__ import annotations

import html
import re
import subprocess
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

from .cleaning import clean_label
from .constants import ENROLMENT_DIR, ENROLMENT_ROWS_PER_PAGE, ENROLMENT_TEMPLATE
from .inputs import locate_inputs
from .targeting import load_councils

TICK = ('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:ascii="Segoe UI Symbol" '
        'w:hAnsi="Segoe UI Symbol"/><w:b/></w:rPr><w:t>✓</w:t></w:r></w:p>')


def esc(value) -> str:
    """Text made safe for Word XML."""
    return html.escape("" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value), quote=False)


def top_level(xml: str, open_tag: str, close_tag: str, inner_tbl: bool = True) -> list[tuple[int, int]]:
    """(start, end) of each element at nesting depth 0, ignoring the same tags inside nested tables."""
    spans, depth, tbl, start = [], 0, 0, None
    for m in re.finditer(r"<w:tbl>|</w:tbl>|" + re.escape(open_tag) + r"[ >/]|" + re.escape(close_tag), xml):
        g = m.group(0)
        if g == "<w:tbl>" and open_tag != "<w:tbl":
            tbl += 1
        elif g == "</w:tbl>" and open_tag != "<w:tbl":
            tbl -= 1
        elif g.startswith(open_tag) and tbl == 0:
            if depth == 0:
                start = m.start()
            depth += 1
        elif g == close_tag and tbl == 0:
            depth -= 1
            if depth == 0:
                spans.append((start, m.end()))
    return spans


def load_template(path: Path) -> dict:
    """Split the template's document.xml into the pieces a page is assembled from."""
    with zipfile.ZipFile(path) as z:
        files = {n: z.read(n) for n in z.namelist()}
    x = files["word/document.xml"].decode("utf-8")
    x = re.sub(r' w14:(?:paraId|textId)="[0-9A-F]+"', "", x)  # ids must be unique, and pages are repeated
    body = x.index("<w:body>") + len("<w:body>")
    t0 = x.index("<w:tbl>", body)
    depth, t1 = 0, None
    for m in re.finditer(r"<w:tbl>|</w:tbl>", x[t0:]):
        depth += 1 if m.group(0) == "<w:tbl>" else -1
        if depth == 0:
            t1 = t0 + m.end()
            break
    table = x[t0:t1]
    rows = []  # top-level rows of the main table
    depth, start = 0, None
    for m in re.finditer(r"<w:tbl>|</w:tbl>|<w:tr[ >]|</w:tr>", table):
        g = m.group(0)
        if g == "<w:tbl>":
            depth += 1
        elif g == "</w:tbl>":
            depth -= 1
        elif g.startswith("<w:tr") and depth == 1:
            start = m.start()
        elif g == "</w:tr>" and depth == 1:
            rows.append((start, m.end()))
    first_hh = next(i for i, (a, b) in enumerate(rows) if "HHSeq1" in table[a:b])
    return dict(files=files, head=x[:body], pre=x[body:t0],
                table_head=table[:rows[first_hh][0]], row=table[rows[first_hh][0]:rows[first_hh][1]],
                table_tail=table[rows[-1][1]:], after=x[t1:])


def fill_fields(xml: str, values: dict) -> str:
    """Replace every MERGEFIELD (simple, empty-simple or complex) with its value from `values` ('' if absent)."""
    def name(instr):
        return re.search(r"MERGEFIELD\s+(\S+)", instr).group(1)

    def run(v, rpr=""):
        return f'<w:r>{rpr}<w:t xml:space="preserve">{esc(v)}</w:t></w:r>' if v != "" else ""

    # complex fields: begin / instrText / separate / result / end
    xml = re.sub(r'<w:r>(?:<w:rPr>(?:(?!</w:r>).)*?</w:rPr>)?<w:fldChar w:fldCharType="begin"/></w:r>'
                 r'<w:r>(?:<w:rPr>(?:(?!</w:r>).)*?</w:rPr>)?<w:instrText[^>]*>([^<]*)</w:instrText></w:r>'
                 r'.*?<w:fldChar w:fldCharType="end"/></w:r>',
                 lambda m: run(values.get(name(m.group(1)), "")), xml, flags=re.S)
    # simple fields with a «placeholder» result: keep the run's formatting
    xml = re.sub(r'<w:fldSimple w:instr="([^"]*)">(<w:r>(?:<w:rPr>.*?</w:rPr>)?)<w:t>[^<]*</w:t></w:r></w:fldSimple>',
                 lambda m: run(values.get(name(m.group(1)), ""), re.sub(r"^<w:r>", "", m.group(2))), xml, flags=re.S)
    # empty simple fields
    xml = re.sub(r'<w:fldSimple w:instr="([^"]*)"/>', lambda m: run(values.get(name(m.group(1)), "")), xml)
    return xml


def fill_after_label(xml: str, label: str, value: str) -> str:
    """Put `value` in the (empty) table cell that follows the cell labelled `label`."""
    off = len("<w:tbl>") if xml.startswith("<w:tbl>") else 0  # the table's own cells sit at depth 0 inside it
    cells = [(a + off, b + off) for a, b in top_level(xml[off:], "<w:tc", "</w:tc>")]
    for i, (a, b) in enumerate(cells[:-1]):
        if "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", xml[a:b])).strip() == label:
            c0, c1 = cells[i + 1]
            cell = xml[c0:c1]
            cell = re.sub(r"<w:p( [^>]*)?/>", lambda m: f"<w:p{m.group(1) or ''}><w:r><w:t xml:space=\"preserve\">"
                          f"{esc(value)}</w:t></w:r></w:p>", cell, count=1) if re.search(r"<w:p( [^>]*)?/>", cell) else \
                re.sub(r"</w:p>", f'<w:r><w:t xml:space="preserve">{esc(value)}</w:t></w:r></w:p>', cell, count=1)
            return xml[:c0] + cell + xml[c1:]
    return xml


def household_row(row: str, seq: int, hh: dict) -> str:
    """One household row: fields filled, OAP/PA boxes removed, CGP/OVC boxes ticked as eligible."""
    row = fill_fields(row, {"HHSeq1": seq, "HHID1": hh["Household ID"], "HeadName1": hh["Household Head"],
                            "HeadID1": hh["Household Head ID"]})
    n0 = row.index("<w:tbl>")
    n1 = row.index("</w:tbl>", n0) + len("</w:tbl>")
    nested = row[n0:n1]
    nested = re.sub(r"(<w:tblGrid>(?:<w:gridCol [^>]*/>){2})(?:<w:gridCol [^>]*/>)+(</w:tblGrid>)", r"\1\2", nested)
    inner = nested[len("<w:tbl>"):-len("</w:tbl>")]  # rows of this table sit at depth 0 inside it
    spans = top_level(inner, "<w:tr", "</w:tr>")
    out = []
    for r0, r1 in spans:
        tr = inner[r0:r1]
        cells = top_level(tr, "<w:tc", "</w:tc>")
        label = "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", tr[cells[0][0]:cells[0][1]])).strip()
        ticked = hh["CGP"] if label == "CGP" else hh["OVC"]
        box = tr[cells[1][0]:cells[1][1]]
        if ticked:
            box = re.sub(r"<w:p( [^>]*)?/>|<w:p( [^>]*)?>.*?</w:p>", TICK, box, count=1, flags=re.S)
        out.append(tr[:cells[0][0]] + tr[cells[0][0]:cells[0][1]] + box + tr[cells[-1][1]:])  # keep label + its box
    nested = "<w:tbl>" + inner[:spans[0][0]] + "".join(out) + "</w:tbl>"
    return row[:n0] + nested + row[n1:]


def page_xml(T: dict, k: int, loc: dict, households: list[dict], first_seq: int) -> str:
    """One filled copy of the form page; pages after the first start on a new page."""
    pre = T["pre"].replace('<wp:docPr id="1"', f'<wp:docPr id="{k + 1}"')  # drawing ids must be unique
    if k:
        first_p = re.search(r"<w:p(?: [^>]*)?>", pre)
        p_end = first_p.end()
        if pre.startswith("<w:pPr>", p_end):
            pre = pre[:p_end + 7] + "<w:pageBreakBefore/>" + pre[p_end + 7:]
        else:
            pre = pre[:p_end] + "<w:pPr><w:pageBreakBefore/></w:pPr>" + pre[p_end:]
    head = fill_fields(T["table_head"], {"District": loc["District"], "CommunityCouncil": loc["Council"],
                                         "ListGenerationDate": loc["Date"], "Number": ""})
    head = fill_after_label(head, "Village", loc["Village"])
    head = fill_after_label(head, "EA", loc["EA"])
    rows = "".join(household_row(T["row"], first_seq + i, h) for i, h in enumerate(households))
    return pre + head + rows + T["table_tail"]


def village_eas(nissa: Path) -> dict:
    """Village name (System Listing_Village Name) -> its EA code(s) from PackageEvent_OrgUnitName_EA."""
    h = pd.read_excel(nissa, sheet_name="EnumeratedHouseholds",
                      usecols=["System Listing_Village Name", "Original_VillageName", "PackageEvent_OrgUnitName_EA"])
    v = clean_label(h["System Listing_Village Name"])
    h["Village"] = v.where(v != "", clean_label(h["Original_VillageName"]))
    h["EA"] = h["PackageEvent_OrgUnitName_EA"].map(lambda e: "" if pd.isna(e) else str(e).removesuffix(".0").strip())
    h = h[h["EA"] != ""]
    # Some households carry a short council-level code (e.g. Tosing '76603') or a place name instead of
    # a code (Menkhoaneng 'St.Dominic'). A village shows its numeric codes of the council's usual length;
    # only when it has none do shorter codes, and then other values, appear.
    numeric = h["EA"].str.isdigit()
    usual = h.loc[numeric, "EA"].str.len().mode().iat[0] if numeric.any() else 0

    def codes(s):
        """The village's EA codes: proper codes first, falling back to whatever is recorded."""
        s = set(s)
        digits = {e for e in s if e.isdigit()}
        proper = {e for e in digits if len(e) >= usual}
        return ", ".join(sorted(proper or digits or s))
    return h.groupby("Village")["EA"].agg(codes).to_dict()


def to_pdf(docx_files: list[Path]):
    """Convert .docx files to PDF next to them with Microsoft Word (Windows)."""
    paths = ";".join(str(p.resolve()) for p in docx_files)
    script = ("$w = New-Object -ComObject Word.Application; $w.Visible = $false; $w.DisplayAlerts = 0; try { "
              f"foreach ($f in '{paths}'.Split(';')) {{ $d = $w.Documents.Open($f, $false, $true); "
              "$d.ExportAsFixedFormat([IO.Path]::ChangeExtension($f, 'pdf'), 17); $d.Close(0) } } "
              "finally { $w.Quit() }")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], check=True)


def build_enrolment(out_root: Path, base: Path = Path(".")) -> bool:
    """Write one enrolment invitation document (.docx and .pdf) per council."""
    template = base / ENROLMENT_TEMPLATE
    if not template.exists():
        print(f"\n   ! enrolment template not found: {template}")
        return False
    councils = load_councils(out_root, base)
    if not councils:
        print("\n   ! no saved council results found - run the analysis first (--all or --council)")
        return False
    T = load_template(template)
    today = date.today().strftime("%d/%m/%Y")
    folder = out_root / ENROLMENT_DIR
    word_dir = folder / "Word"
    word_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n=== Enrolment invitation lists ({ENROLMENT_ROWS_PER_PAGE} households per page, a new page per village) ===")
    written = []
    for R, lists in councils:
        cgp, ovc = lists["CGP"], lists["OVC-B"]
        hh = pd.concat([cgp, ovc]).drop_duplicates("Household ID").copy()
        hh["CGP"] = hh["Household ID"].isin(set(cgp["Household ID"]))
        hh["OVC"] = hh["Household ID"].isin(set(ovc["Household ID"]))
        hh = hh.sort_values(["Village", "PMT", "Household ID"])  # villages A-Z, poorest household first
        nissa = locate_inputs(base, R["council"])["nissa"]
        eas = village_eas(nissa) if nissa else {}
        pages, k = [], 0
        for village, g in hh.groupby("Village", sort=True):
            recs = g.to_dict("records")
            loc = dict(District=g["District"].iat[0], Council=R["council"], Village=village,
                       EA=eas.get(village, ""), Date=today)
            for start in range(0, len(recs), ENROLMENT_ROWS_PER_PAGE):
                pages.append(page_xml(T, k, loc, recs[start:start + ENROLMENT_ROWS_PER_PAGE], start + 1))
                k += 1
        doc = T["head"] + "".join(pages) + T["after"]
        path = word_dir / f"Enrolment_Invitation_List_{R['council']}.docx"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for n, data in T["files"].items():
                z.writestr(n, doc.encode("utf-8") if n == "word/document.xml" else data)
        written.append(path)
        print(f"   {R['council']:12s} {hh['Village'].nunique():4d} villages, {len(hh):4d} households "
              f"(CGP {int(hh['CGP'].sum())}, OVC {int(hh['OVC'].sum())}, both {int((hh['CGP'] & hh['OVC']).sum())}), {k} pages")
    print("   converting to PDF with Microsoft Word ...")
    to_pdf(written)
    for p in written:
        target = folder / p.with_suffix(".pdf").name
        target.unlink(missing_ok=True)
        p.with_suffix(".pdf").rename(target)
    print(f"   -> {folder} (PDFs; the Word versions are in {word_dir.name}/)")
    return True

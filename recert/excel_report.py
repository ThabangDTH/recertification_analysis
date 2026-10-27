"""The Excel workbook: Summary sheet with tables and charts, plus one sheet per list."""

from __future__ import annotations

import io
import math
import re
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

from .constants import OVCB_MAX_AGE, OVCB_MIN_AGE


def write_excel(R: dict, S: dict, T: dict, path: Path):
    """Write the stakeholder workbook: a Summary sheet with tables and bar charts, then one sheet per list."""
    with pd.ExcelWriter(path, engine="xlsxwriter", date_format="yyyy-mm-dd", datetime_format="yyyy-mm-dd") as xw:
        wb = xw.book
        f_title = wb.add_format({"bold": True, "font_size": 16, "font_color": "#184f95"})
        f_sub = wb.add_format({"font_color": "#52514e"})
        f_sec = wb.add_format({"bold": True, "font_size": 12, "font_color": "#184f95"})
        f_head_line = wb.add_format({"bold": True, "bg_color": "#184f95", "font_color": "white", "valign": "vcenter",
                                     "border": 1, "border_color": "#184f95"})
        f_head = wb.add_format({"bold": True, "bg_color": "#184f95", "font_color": "white", "text_wrap": True,
                                "valign": "vcenter", "border": 1, "border_color": "#184f95"})
        f_cell = wb.add_format({"border": 1, "border_color": "#d9d9d9", "valign": "top"})
        f_num = wb.add_format({"border": 1, "border_color": "#d9d9d9", "num_format": "#,##0", "bold": True})
        # at-a-glance numbers are text like "4,256 Households (8,593 Children)": bold and right-aligned like numbers
        f_numtext = wb.add_format({"border": 1, "border_color": "#d9d9d9", "bold": True, "align": "right"})
        f_green = wb.add_format({"bg_color": "#dff3df", "font_color": "#006300"})
        f_red = wb.add_format({"bg_color": "#fbe2e2", "font_color": "#9c1c1c"})
        f_blue = wb.add_format({"bg_color": "#e3eefc", "font_color": "#184f95"})
        f_amber = wb.add_format({"bg_color": "#fff1d1", "font_color": "#7a5200"})

        # ---------------- Summary sheet: tables + native Excel bar charts ----------------
        ws = wb.add_worksheet("Summary")
        xw.sheets["Summary"] = ws
        ws.hide_gridlines(2)
        ws.set_column(0, 0, 46)
        ws.set_column(1, 1, 36)  # room for "17,424 Households (45,315 Children)"
        ws.set_column(2, 2, 14)
        ws.set_column(3, 3, 58)
        ws.write(0, 0, f"Social Assistance Recertification Analysis - {S['council']}", f_title)
        place = (",".join(c["council"] for c in R["council_summaries"]) if R.get("combined")
                 else S["district_label"])  # the combined workbook lists its councils
        ws.write(1, 0, f"{place}  |  prepared {date.today().strftime('%d %B %Y')}", f_sub)

        def table(df, row, title, num_cols=(), text_num_cols=()):
            """Write a titled table on the Summary sheet; returns its first and last data rows."""
            ws.write(row, 0, title, f_sec)
            row += 1
            for j, c in enumerate(df.columns):
                ws.write(row, j, c, f_head)
            for i, r in enumerate(df.itertuples(index=False), start=1):
                for j, v in enumerate(r):
                    if df.columns[j] in num_cols and v != "" and pd.notna(v):  # blank = not available
                        ws.write_number(row + i, j, float(v), f_num)
                    elif df.columns[j] in text_num_cols:
                        ws.write_string(row + i, j, str(v), f_numtext)
                    else:
                        ws.write(row + i, j, v, f_cell)
            return row + 1, row + len(df)  # first and last data row

        def bar_chart(title, cat_rows, val_col, anchor, color, height=None, cat_col=0, colors=None, width=560,
                      hidden_data=False, x_offset=12, small_labels=False):
            """Add a horizontal bar chart for a Summary table (data labels, no legend)."""
            r0, r1 = cat_rows
            ch = wb.add_chart({"type": "bar"})
            series = {"categories": ["Summary", r0, cat_col, r1, cat_col],
                      "values": ["Summary", r0, val_col, r1, val_col],
                      "fill": {"color": color}, "border": {"none": True}, "gap": 60,
                      "data_labels": {"value": True, "num_format": "#,##0"}}
            if colors:
                series["points"] = [{"fill": {"color": c}, "border": {"none": True}} for c in colors]
            ch.add_series(series)
            if hidden_data:  # Excel skips hidden cells unless told otherwise
                ch.show_hidden_data()
            ch.set_title({"name": title, "name_font": {"size": 11, "bold": True}})
            ch.set_legend({"none": True})
            y_axis = {"reverse": True, "major_gridlines": {"visible": False}, "line": {"color": "#c3c2b7"}}
            if small_labels:
                y_axis.update(num_font={"size": 8}, interval_unit=1)  # show every category label
            ch.set_y_axis(y_axis)
            ch.set_x_axis({"major_gridlines": {"visible": True, "line": {"color": "#e1e0d9"}}, "num_format": "#,##0",
                           "min": 0})
            ch.set_chartarea({"border": {"color": "#e1e0d9"}})
            ch.set_size({"width": width, "height": height or max(200, 60 + 34 * (r1 - r0 + 1))})
            ws.insert_chart(anchor, ch, {"x_offset": x_offset, "y_offset": 0})

        row = 3
        glance_rows = {}
        for key, title in (("hh_glance", "Households at a glance"),
                           ("cgp_glance", "CGP (Child Grant Programme) at a glance"),
                           ("pa_glance", "PA (Public Assistance) at a glance"),
                           ("ovcb_glance", "OVC-B (Orphans and Vulnerable Children Bursary) at a glance")):
            first, end = table(T[key], row, title, text_num_cols=("Number",))
            glance_rows[key] = (row, first)  # heading row, first data row ("Eligible Poor households")
            row = end + 3

        # PA and OVC-B charts beside their tables (Poor vs Ultra-Poor households; OVC-B children by age)
        ROW_PX = 20
        pa_head, pa_first = glance_rows["pa_glance"]
        ov_head, ov_first = glance_rows["ovcb_glance"]
        # the Number column is text, so the household charts read numeric copies kept in hidden column AJ
        for r0, (poor, ultra) in ((pa_first, (S["pa_hh_poor"], S["pa_hh_ultra"])),
                                  (ov_first, (S["ovcb_hh_poor"], S["ovcb_hh_ultra"]))):
            ws.write_number(r0, 35, poor)
            ws.write_number(r0 + 1, 35, ultra)
        ws.set_column(35, 35, None, None, {"hidden": True})
        bar_chart("PA: eligible households", (pa_first, pa_first + 1), 35, f"F{pa_head + 1}", "#2a78d6",
                  height=(ov_head - pa_head) * ROW_PX - 10, width=440, hidden_data=True)
        ov_height = max(150, (row - ov_head) * ROW_PX - 10)
        bar_chart("OVC-B: eligible households", (ov_first, ov_first + 1), 35, f"F{ov_head + 1}", "#2a78d6",
                  height=ov_height, width=440, hidden_data=True)
        ages = R["ovcb"]["Age"].value_counts()  # children by age, kept in hidden columns AC:AD for the chart
        for i, a in enumerate(range(OVCB_MIN_AGE, OVCB_MAX_AGE + 1)):
            ws.write(ov_head + i, 28, f"Age {a}")
            ws.write_number(ov_head + i, 29, int(ages.get(a, 0)))
        ws.set_column(28, 29, None, None, {"hidden": True})
        bar_chart("OVC-B: eligible children by age", (ov_head, ov_head + OVCB_MAX_AGE - OVCB_MIN_AGE), 29,
                  f"F{ov_head + 1}", "#2a78d6", height=ov_height, width=440, cat_col=28, hidden_data=True,
                  x_offset=12 + 440 + 12, small_labels=True)
        bc = T.get("by_council")
        if bc is not None:
            num = [c for c in bc.columns if c not in ("Community Council", "Match Rate")]
            rng = table(bc, row, "Results by community council", num_cols=num)
            for j in range(4, len(bc.columns)):
                ws.set_column(j, j, 13)
            # chart sits below this wide table: eligible children per council
            # OVC-B households per council are not a table column: keep them in hidden columns AF:AG for their chart
            for i, cs in enumerate(R["council_summaries"]):  # same order as the table rows
                ws.write(rng[0] + i, 31, cs["council"])
                ws.write_number(rng[0] + i, 32, cs["ovcb_hh"])
            ws.set_column(31, 32, None, None, {"hidden": True})
            # one row of charts below the table, ordered by programme
            by_council_charts = (
                ("CGP eligible households by community council", bc.columns.get_loc("Eligible Households"), 0, False),
                ("CGP eligible children by community council", bc.columns.get_loc("Eligible Children"), 0, False),
                ("PA eligible households by community council", bc.columns.get_loc("PA Eligible Households"), 0, False),
                ("OVC-B eligible households by community council", 32, 31, True),
                ("OVC-B eligible children by community council", bc.columns.get_loc("OVC-B Eligible Children"), 0, False),
            )
            for k, (title, val_col, cat_col, hidden) in enumerate(by_council_charts):
                bar_chart(title, rng, val_col, f"A{rng[1] + 3}", "#2a78d6", width=440,
                          height=max(200, 60 + 34 * len(bc)), x_offset=12 + k * (440 + 12), cat_col=cat_col,
                          hidden_data=hidden, small_labels=True)
            row = rng[1] + 3 + max(16, int((60 + 34 * len(bc)) / 20) + 2)
        if T["cv_summary"] is not None:
            rng = table(T["cv_summary"], row, "Community validation results", num_cols=("Households",))
            row = rng[1] + 2
            if len(T["cv_changes"]):
                rng2 = table(T["cv_changes"], row, "How the CBC changed (before → after validation)",
                             num_cols=("Households",))
                h = max(240, 60 + 30 * len(T["cv_changes"]))
                bar_chart("CBC changes from community validation", rng2, 1, f"F{rng[0] - 1}", "#2a78d6", height=h)
                row = max(rng2[1] + 3, rng[0] - 1 + math.ceil(h / 20) + 3)  # rows are ~20px tall
            else:
                row += 1
            ws.write(row - 2, 0, "Full list of validated households: see the CommunityValidation sheet.", f_sub)
        else:
            ws.write(row, 0, "Community validation results", f_sec)
            ws.write(row + 1, 0, "No community validation data was received for this council.", f_sub)
            row += 4
        rng = table(T["by_cbc"], row, "Households by community classification", num_cols=("Households",))
        bar_chart("Households by community classification", rng, 1, f"F{row + 1}", "#2a78d6")
        row = max(rng[1] + 3, row + 12)
        rng = table(T["outcome"], row, "What happens to children already in the programme",
                    num_cols=("Children", "Households"))
        bar_chart("Children already in programme", rng, 1, f"F{row + 1}", "#eb6834", height=230,
                  colors=["#2a78d6", "#eb6834", "#eda100"])
        row = max(rng[1] + 3, row + 14)
        if len(T["exit_reasons"]):
            rng = table(T["exit_reasons"], row, "Reasons for exiting the program", num_cols=("Children",))
            bar_chart("Reasons for exiting the program", rng, 1, f"F{row + 1}", "#eb6834")
            row = max(rng[1] + 3, row + 4 + 2 * len(T["exit_reasons"]) + 6)

        # Match result: chart only. Its data sits in hidden columns Z:AA.
        mq = T["match_quality"]
        ws.write(row, 0, "Match Result of Beneficiaries In Program against NISSA data", f_sec)
        for i, r in enumerate(mq.itertuples(index=False)):
            ws.write(row + 1 + i, 25, r[0])
            ws.write_number(row + 1 + i, 26, r[1])
        ws.set_column(25, 26, None, None, {"hidden": True})
        bar_chart("Match Result of Beneficiaries In Program against NISSA data", (row + 1, row + len(mq)), 26,
                  f"A{row + 2}", "#2a78d6", height=300, cat_col=25, width=820,
                  colors=["#2a78d6", "#2a78d6", "#2a78d6", "#eda100", "#eda100"], hidden_data=True)
        ws.write(row + 17, 0, "Children with a Low Match or No Match are not exited. They are flagged for "
                              "investigation (see the FlaggedForInvestigation sheet).", f_sub)

        # ---------------- data sheets ----------------
        def sheet(df, name, status_col=None):
            """Write one data sheet with a coloured header, fitted column widths, a filter and status colours."""
            df.to_excel(xw, sheet_name=name, index=False)
            w = xw.sheets[name]
            for j, c in enumerate(df.columns):
                w.write(0, j, c, f_head_line)
                longest = df[c].dropna().astype(str).str.len().max() if df[c].notna().any() else 0
                if pd.api.types.is_datetime64_any_dtype(df[c]):
                    longest = 10  # yyyy-mm-dd
                # bold header plus room for the filter arrow
                w.set_column(j, j, max(len(c) * 1.1 + 4, longest * 1.1 + 2))
            w.freeze_panes(1, 0)
            w.autofilter(0, 0, max(len(df), 1), len(df.columns) - 1)
            if status_col and status_col in df.columns and len(df):
                j = df.columns.get_loc(status_col)
                for val, fm in (("Remaining", f_green), ("Exiting", f_red), ("Proposed", f_blue), ("Flagged", f_amber),
                                ("CBC changed", f_blue), ("Not applied", f_amber), ("No change in CV", f_amber),
                                ("Remove", f_amber), ("Check", f_amber), ("Investigate", f_amber),
                                ("Low Match", f_amber), ("No Match", f_amber)):
                    w.conditional_format(1, j, len(df), j, {"type": "text", "criteria": "begins with",
                                                            "value": val, "format": fm})

        if T["cv_sheet"] is not None:
            sheet(T["cv_sheet"], "CommunityValidation", "Result")
        sheet(T["poor_hh"], "PoorHouseholds")
        sheet(T["eligible_hh"], "EligibleHouseholds", "Status")
        sheet(T["eligible_children"], "EligibleChildren", "Status")
        sheet(T["already"], "AlreadyInProgram", "Decision")
        sheet(T["remaining"], "RemainingInProgram")
        sheet(T["exiting"], "ExitingProgram", "Action Needed")
        sheet(T["flagged"], "FlaggedForInvestigation", "Match Result")
        sheet(T["new_entrants"], "ProposedNewEntrants")
        sheet(T["pa_hh"], "PA_EligibleHouseholds")
        sheet(T["ovcb_children"], "OVCB_EligibleChildren")


def force_row_height(path: Path, keep=("Summary",), height=15):
    """Make every row of the data sheets exactly `height` points.

    xlsxwriter never writes a height equal to its 15pt default, and without an explicit custom
    height Excel picks its own default (14.3 on some screens), so mark the sheets' default
    row height as custom directly in the saved file."""
    with zipfile.ZipFile(path) as z:
        files = {n: z.read(n) for n in z.namelist()}
    names = re.findall(r'<sheet name="([^"]+)"', files["xl/workbook.xml"].decode("utf-8"))
    for i, name in enumerate(names, start=1):
        key = f"xl/worksheets/sheet{i}.xml"
        if name in keep or key not in files:
            continue
        x = files[key].decode("utf-8")
        x = re.sub(r"<sheetFormatPr[^>]*/>", f'<sheetFormatPr defaultRowHeight="{height}" customHeight="1"/>', x, count=1)
        files[key] = x.encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, data in files.items():
            z.writestr(n, data)
    path.write_bytes(buf.getvalue())

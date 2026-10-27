"""The one-page HTML dashboard: tiles, key findings and chart + table sections."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .constants import CV_CHANGED, OVCB_MAX_AGE, OVCB_MIN_AGE
from .dashboard_template import DASH_TEMPLATE
from .formatting import esc, fmt, pct


def svg_hbars(items, bar_h=26, gap=12, total=None):
    """Horizontal bars with value and share labels. items: [(label, value, css colour var)]"""
    vmax = max([v for _, v, _ in items] + [1])
    label_w = 20 + 7.8 * max([len(str(l)) for l, _, _ in items] + [10])  # room for the longest label
    width = label_w + 340
    h = len(items) * (bar_h + gap) + 2
    plot_w = width - label_w - 110
    out = []
    for i, (label, v, col) in enumerate(items):
        y = i * (bar_h + gap)
        w = max(3, plot_w * v / vmax) if v else 0
        share = f" ({pct(v, total)})" if total else ""
        out.append(f'<text x="{label_w - 12}" y="{y + bar_h / 2 + 5}" text-anchor="end" class="lbl">{esc(label)}</text>')
        if w:
            out.append(f'<rect x="{label_w}" y="{y}" width="{w:.1f}" height="{bar_h}" rx="4" fill="var({col})" '
                       f'class="mark" tabindex="0" data-tip="{esc(label)}: {fmt(v)}{share}"/>')
        out.append(f'<text x="{label_w + w + 10:.1f}" y="{y + bar_h / 2 + 5}" class="val">{fmt(v)}'
                   f'<tspan class="share">{esc(share)}</tspan></text>')
    out.append(f'<line x1="{label_w}" x2="{label_w}" y1="-4" y2="{h - gap + 4}" class="axis"/>')
    return f'<svg viewBox="0 0 {width} {h}" width="100%" role="img">{"".join(out)}</svg>'


def html_table(df: pd.DataFrame, cls="tbl"):
    """Render a DataFrame as an HTML table (numbers right-aligned)."""
    head = "".join(f'<th class="{"num" if pd.api.types.is_numeric_dtype(df[c]) else ""}">{esc(c)}</th>' for c in df.columns)
    body = []
    for row in df.itertuples(index=False):
        tds = []
        for v in row:
            num = isinstance(v, (int, float, np.integer, np.floating))
            tds.append(f'<td class="{"num" if num else ""}">{fmt(v) if num else esc(v)}</td>')
        body.append("<tr>" + "".join(tds) + "</tr>")
    return f'<table class="{cls}"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def card(title, desc, chart, table, full=False):
    """A dashboard section: title, description, then a chart beside its table (chart only when no table)."""
    if not table:
        return (f'<section class="card"><h2>{esc(title)}</h2><p class="desc">{esc(desc)}</p>'
                f'<div class="chart solo">{chart}</div></section>')
    return (f'<section class="card{" full" if full else ""}"><h2>{esc(title)}</h2><p class="desc">{esc(desc)}</p>'
            f'<div class="split"><div class="chart">{chart}</div><div class="tablewrap">{table}</div></div></section>')


def write_dashboard(R: dict, S: dict, T: dict, path: Path):
    """Write the one-page HTML dashboard: tiles, key findings and chart + table sections."""
    n_ben = S["ben_children"]
    b = S["baseline"]
    groups = [
        ("Households", ([
            ("Baseline households (old NISSA data)", b["hh"],
             f"{fmt(b['poor'])} Poor · {fmt(b['ultra'])} Ultra-Poor at baseline", "")] if b else []) + [
            ("Households visited (updated NISSA data)", S["hh_enumerated"],
             f"{pct(S['hh_enumerated'], b['hh'])} of the baseline number" if b
             else f"{fmt(S['hh_with_pmt'])} with a PMT score", ""),
            ("Poor households", S["hh_poor_only"], f"{pct(S['hh_poor_only'], S['hh_enumerated'])} of households visited", ""),
            ("Ultra-Poor households", S["hh_ultra"], f"{pct(S['hh_ultra'], S['hh_enumerated'])} of households visited", ""),
        ]),
        ("CGP · Child Grant Programme", [
            ("Eligible households", S["hh_eligible"],
             f"{fmt(S['hh_eligible_poor'])} Poor · {fmt(S['hh_eligible_ultra'])} Ultra-Poor", ""),
            ("Eligible children", S["children_eligible"], f"{fmt(S['children_ages_out_12m'])} turn 18 within 12 months", ""),
            ("Already in programme", n_ben, f"children in {fmt(S['ben_households'])} households", ""),
            ("Match rate", f"{100 * S['match_rate']:.1f}%", f"{fmt(S['matched'])} of {fmt(n_ben)} found in NISSA", ""),
            ("Remaining", S["remain_children"], f"children · {fmt(S['prog_hh_remain'])} households", "k-remain"),
            ("Exiting", S["exit_children"], f"children · {fmt(S['prog_hh_exit'])} households", "k-exit"),
            ("Flagged for investigation", S["flag_children"], "children · need checking, not exited", "k-flag"),
            ("Proposed new entrants", S["new_children"], f"children · {fmt(S['hh_new'])} households", "k-new"),
        ]),
        ("PA · Public Assistance", [
            ("Eligible households", S["pa_hh"], f"{fmt(S['pa_hh_poor'])} Poor · {fmt(S['pa_hh_ultra'])} Ultra-Poor", ""),
            ("People in eligible households", S["pa_people"], "Poor/Ultra-Poor households with no member aged 0-17", ""),
        ]),
        ("OVC-B · Orphans and Vulnerable Children Bursary", [
            ("Eligible children (12-17)", S["ovcb_children"],
             f"{fmt(S['ovcb_boys'])} boys · {fmt(S['ovcb_girls'])} girls", ""),
            ("Eligible households", S["ovcb_hh"], f"{fmt(S['ovcb_hh_poor'])} Poor · {fmt(S['ovcb_hh_ultra'])} Ultra-Poor", ""),
        ]),
    ]
    kpi_html = "".join(
        f'<h2 class="grp">{esc(title)}</h2><div class="kpis">'
        + "".join(f'<div class="kpi {cls}"><div class="kpi-l">{esc(l)}</div><div class="kpi-v">{fmt(v)}</div>'
                  f'<div class="kpi-s">{esc(s_)}</div></div>' for l, v, s_, cls in tiles)
        + "</div>" for title, tiles in groups)

    er = T["exit_reasons"]
    findings = [
        f"<b>{pct(S['hh_poor'], S['hh_enumerated'])}</b> of households visited are Poor or Ultra-Poor. "
        f"<b>{fmt(S['hh_eligible'])}</b> of them have at least one child aged 0–17 and qualify for the Child Grant Programme.",
        f"<b>{fmt(S['children_eligible'])}</b> children qualify: <b>{fmt(S['remain_children'])}</b> are already in the programme "
        f"and <b>{fmt(S['new_children'])}</b> are proposed new entrants.",
        f"Of the <b>{fmt(n_ben)}</b> children already in the programme, <b>{fmt(S['matched'])}</b> "
        f"(<b>{100 * S['match_rate']:.1f}%</b>) were found in the NISSA data.",
        f"<b>{fmt(S['remain_children'])}</b> children remain in the programme, <b>{fmt(S['exit_children'])}</b> exit and "
        f"<b>{fmt(S['flag_children'])}</b> are flagged for investigation.",
    ]
    if len(er):
        findings.append(f"The most common exit reason is: <b>{esc(er.iloc[0, 0])}</b> "
                        f"({fmt(er.iloc[0, 1])} of {fmt(S['exit_children'])} exiting children).")
    if S["duplicates"]:
        findings.append(f"<b>{fmt(S['duplicates'])}</b> children are listed twice in the programme. "
                        "Remove the duplicate records (see the ExitingProgram sheet).")
    if S["flag_children"]:
        findings.append(f"<b>{fmt(S['flag_children'])}</b> children need checking, mostly because they had only a low match "
                        "or no match in the NISSA data. "
                        "They are not exited; investigate them (see the FlaggedForInvestigation sheet).")
    if S["children_ages_out_12m"]:
        findings.append(f"<b>{fmt(S['children_ages_out_12m'])}</b> eligible children turn 18 within the next 12 months.")
    if S["cv"]:
        findings.insert(1, f"Community validation reviewed <b>{fmt(S['cv']['records'])}</b> households and changed the CBC of "
                           f"<b>{fmt(S['cv']['results'][CV_CHANGED])}</b>: <b>{fmt(S['cv']['into_poor'])}</b> moved into "
                           f"Poor/Ultra-Poor and <b>{fmt(S['cv']['out_of_poor'])}</b> moved out. All figures below include these changes.")
    findings.append(f"PA: <b>{fmt(S['pa_hh'])}</b> Poor/Ultra-Poor households have no member aged 0–17 "
                    f"(<b>{fmt(S['pa_hh_poor'])}</b> Poor, <b>{fmt(S['pa_hh_ultra'])}</b> Ultra-Poor; "
                    f"{fmt(S['pa_people'])} people) and qualify for Public Assistance.")
    findings.append(f"OVC-B: <b>{fmt(S['ovcb_children'])}</b> children aged 12–17 in <b>{fmt(S['ovcb_hh'])}</b> Poor/Ultra-Poor "
                    "households qualify for the OVC Bursary.")
    findings_html = "".join(f"<li>{f}</li>" for f in findings)

    by_cbc = T["by_cbc"]
    cbc_chart = svg_hbars([(r[0], r[1], "--c-hh") for r in by_cbc.itertuples(index=False)], total=S["hh_enumerated"])

    funnel = pd.DataFrame(([("Baseline households (old NISSA data)", b["hh"])] if b else []) + [
        ("Households visited", S["hh_enumerated"]),
        ("Poor + Ultra-Poor households", S["hh_poor"]),
        ("Eligible households (with a child 0-17)", S["hh_eligible"]),
    ], columns=["Step", "Households"])
    funnel_chart = svg_hbars([(r[0], r[1], "--c-hh") for r in funnel.itertuples(index=False)])

    kids = pd.DataFrame([
        ("Remaining in programme", S["remain_children"], pct(S["remain_children"], S["children_eligible"])),
        ("Proposed new entrants", S["new_children"], pct(S["new_children"], S["children_eligible"])),
        ("Total eligible children", S["children_eligible"], "100%"),
    ], columns=["Eligible children", "Children", "Share"])
    kids_chart = svg_hbars([("Remaining in programme", S["remain_children"], "--c-remain"),
                            ("Proposed new entrants", S["new_children"], "--c-new")], total=S["children_eligible"])

    out_chart = svg_hbars([("Remaining in programme", S["remain_children"], "--c-remain"),
                           ("Exiting programme", S["exit_children"], "--c-exit"),
                           ("Flagged for investigation", S["flag_children"], "--c-check")], total=n_ben)

    exit_chart = (svg_hbars([(r[0], r[1], "--c-exit") for r in er.itertuples(index=False)], total=S["exit_children"])
                  if len(er) else "<p class='desc'>No children exit.</p>")

    mq = T["match_quality"]
    mq_chart = svg_hbars([(r[0], r[1], "--c-check" if r[0].startswith(("Low", "No ")) else "--c-hh")
                          for r in mq.itertuples(index=False)], total=n_ben)

    bc = T.get("by_council")
    if bc is not None:
        bc_chart = svg_hbars([(r["Community Council"], int(r["Eligible Children"]), "--c-hh")
                              for _, r in bc.sort_values("Eligible Children", ascending=False).iterrows()],
                             bar_h=20, gap=9, total=S["children_eligible"])
        place_card = (f'<section class="card"><h2>Results by community council</h2>'
                      f'<p class="desc">CGP eligible children in each council (share of all CGP eligible children), '
                      f'followed by the key figures for each council. Click a column heading to sort.</p>'
                      f'<div class="chart solo">{bc_chart}</div>'
                      f'<div class="scroll" style="margin-top:18px">{html_table(bc, cls="tbl sortable compact")}</div></section>')
    else:
        vt = T["villages"]
        top = vt.head(10)
        village_chart = svg_hbars([(r["Village"], int(r["Eligible Children"]), "--c-hh") for _, r in top.iterrows()],
                                  bar_h=20, gap=9)
        place_card = card("Villages with the most eligible children", "Top 10 villages. The table lists every village; "
                          "click a column heading to sort.", village_chart,
                          f'<div class="scroll">{html_table(vt, cls="tbl sortable")}</div>', full=True)

    cards = (place_card if bc is not None else "") + "".join([
        card("Households", "Households visited, how many are Poor or Ultra-Poor, and how many have children who qualify.",
             funnel_chart, html_table(funnel)),
        card("Households by community classification", "Updated community-based classification (CBC). "
             "Only Poor and Ultra-Poor households are eligible.", cbc_chart, html_table(by_cbc)),
        *([card("Community validation results", "How community validation changed the CBC (before → after). "
                "The full list is in the CommunityValidation sheet.",
                svg_hbars([(r[0], r[1], "--c-hh") for r in T["cv_changes"].itertuples(index=False)],
                          total=S["cv"]["results"][CV_CHANGED]) if len(T["cv_changes"]) else
                "<p class='desc'>No CBC was changed.</p>", html_table(T["cv_summary"]))] if S["cv"] else []),
        card("CGP: eligible children", "Children aged 0–17 in Poor and Ultra-Poor households.", kids_chart, html_table(kids)),
        card("CGP: children already in the programme", "Whether each child already in the programme still qualifies.",
             out_chart, html_table(T["outcome"])),
        card("CGP: reasons for exiting the program", "Exit reasons among children already in the programme, as a share of all exits.",
             exit_chart, html_table(er) if len(er) else ""),
        card("CGP: Match Result of Beneficiaries In Program against NISSA data",
             f"Match rate {100 * S['match_rate']:.1f}%. Children with a Low Match or No Match are not exited; "
             "they are flagged for investigation.", mq_chart, ""),
        card("PA: Public Assistance", "Poor and Ultra-Poor households with no member aged 0–17. "
             "The full list is in the PA_EligibleHouseholds sheet.",
             svg_hbars([("Poor households", S["pa_hh_poor"], "--c-hh"),
                        ("Ultra-Poor households", S["pa_hh_ultra"], "--c-hh")], total=S["pa_hh"]),
             html_table(T["pa_glance"][["Measure", "Number"]])),
        card("OVC-B: Orphans and Vulnerable Children Bursary", "Children aged 12–17 in Poor and Ultra-Poor households, "
             "by age. The full list is in the OVCB_EligibleChildren sheet.",
             svg_hbars([(f"Age {a}", int((R["ovcb"]["Age"] == a).sum()), "--c-hh") for a in range(OVCB_MIN_AGE, OVCB_MAX_AGE + 1)],
                       total=S["ovcb_children"]),
             html_table(T["ovcb_glance"][["Measure", "Number"]])),
    ]) + (place_card if bc is None else "")

    page = (DASH_TEMPLATE.replace("{{TITLE}}", esc(f"Social Assistance Recertification - {S['council']}"))
            .replace("{{COUNCIL}}", esc(S["council"])).replace("{{DISTRICT}}", esc(S["district_label"]))
            .replace("{{RUNDATE}}", esc(date.today().strftime("%d %B %Y")))
            .replace("{{KPIS}}", kpi_html).replace("{{FINDINGS}}", findings_html).replace("{{CARDS}}", cards))
    path.write_text(page, encoding="utf-8")

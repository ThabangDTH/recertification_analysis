"""Running councils end to end, caching their results and building the combined analysis."""

from __future__ import annotations

import pickle
from datetime import datetime
from pathlib import Path

import pandas as pd

from .analysis import analyse
from .constants import CACHE_NAME, COMBINED_NAME, COMBINED_TITLE
from .dashboard import write_dashboard
from .excel_report import force_row_height, write_excel
from .inputs import locate_inputs
from .summary import summarise
from .tables import build_tables


def save_cache(R: dict, folder: Path):
    """Save the parts of a council's results needed for the combined analysis and --rewrite."""
    slim = {k: R[k] for k in ("council", "hh", "elig", "ovcb", "bm", "ph", "params", "cv", "baseline")}
    slim["mem"] = R["mem"][["Is_Active", "Is_Child", "Ages_Out_12m"]]  # all the summary needs
    slim["built"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(folder / CACHE_NAME, "wb") as fh:
        pickle.dump(slim, fh)


def write_outputs(R: dict, S: dict, folder: Path, name: str):
    """Build the tables and write the workbook and dashboard for one council (or the combination)."""
    folder.mkdir(parents=True, exist_ok=True)
    xlsx = folder / f"Recertification_{name}.xlsx"
    dash = folder / f"Dashboard_{name}.html"
    T = build_tables(R, S)
    for writer, target in ((write_excel, xlsx), (write_dashboard, dash)):
        try:
            writer(R, S, T, target)
            if target == xlsx:
                force_row_height(xlsx)
        except PermissionError:
            print(f"   ! could not write {target.name} - it is open in another program. Close it and run again.")
    print(f"   -> {xlsx}\n   -> {dash}")


def build_combined(out_root: Path) -> bool:
    """Combine every council's saved results into one analysis with its own workbook and dashboard."""
    caches = sorted(p for p in out_root.glob(f"*/{CACHE_NAME}") if p.parent.name != COMBINED_NAME)
    if len(caches) < 2:
        print("\n   ! the combined analysis needs at least two councils that have been run")
        return False
    print(f"\n=== {COMBINED_TITLE} ===")
    parts = []
    for c in caches:
        with open(c, "rb") as fh:
            parts.append(pickle.load(fh))
        print(f"   {parts[-1]['council']:12s} results from {parts[-1]['built']}")
    if len({tuple(sorted(r["params"].items())) for r in parts}) > 1:
        print("   ! councils were run with different matching settings - rerun with --all for a consistent combination")
    summaries = [summarise(r) for r in parts]
    R = {k: pd.concat([r[k] for r in parts], ignore_index=True) for k in ("hh", "mem", "elig", "ovcb", "bm", "ph")}

    def stack(key):
        """Concatenate an optional frame (community validation, baseline) over the councils that have it."""
        frames = [r[key] for r in parts if r.get(key) is not None]
        return pd.concat(frames, ignore_index=True) if frames else None

    R.update(council=COMBINED_TITLE, combined=True, council_summaries=summaries, params=parts[0]["params"],
             cv=stack("cv"), baseline=stack("baseline"))
    S = summarise(R)
    print(f"   match rate {100 * S['match_rate']:.1f}%  |  remain {S['remain_children']:,}  exit {S['exit_children']:,}  "
          f"flagged {S['flag_children']:,}  new {S['new_children']:,} children  |  PA {S['pa_hh']:,} households  "
          f"OVC-B {S['ovcb_children']:,} children")
    write_outputs(R, S, out_root / COMBINED_NAME, COMBINED_NAME)
    cols = ["council", "baseline_hh", "hh_enumerated", "hh_poor_only", "hh_ultra", "hh_poor", "hh_eligible", "children_eligible", "ben_children",
            "match_rate", "remain_children", "exit_children", "flag_children", "new_children", "prog_hh_remain",
            "prog_hh_exit", "prog_hh_flag", "hh_new", "pa_hh", "ovcb_hh", "ovcb_children"]
    allp = out_root / "All_Councils_Summary.xlsx"
    try:
        pd.DataFrame(summaries + [S])[cols].to_excel(allp, index=False)
        print(f"   -> {allp}")
    except PermissionError:
        print(f"   ! could not write {allp.name} - it is open in another program.")
    return True


def run_council(base: Path, out_root: Path, council: str, args) -> dict | None:
    """Analyse one council, print its headline figures, write its outputs and cache the results."""
    paths = locate_inputs(base, council)
    missing = [k for k in ("nissa", "inprogram", "pmt") if paths[k] is None]  # the baseline is optional
    if missing:
        print(f"\n=== {council} === SKIPPED - missing input(s): {', '.join(missing)}")
        return None
    R = analyse(council, paths, args.min_score, args.review_score, args.min_name)
    S = summarise(R)
    print(f"   match rate {100 * S['match_rate']:.1f}%  |  remain {S['remain_children']:,}  exit {S['exit_children']:,}  flagged {S['flag_children']:,}  "
          f"new {S['new_children']:,} children  |  PA {S['pa_hh']:,} households  OVC-B {S['ovcb_children']:,} children")
    write_outputs(R, S, out_root / council, council)
    save_cache(R, out_root / council)
    return S

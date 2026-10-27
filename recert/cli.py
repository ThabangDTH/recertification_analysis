"""Command-line interface of the recertification analysis."""

from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

from .constants import CACHE_NAME, COMBINED_NAME
from .inputs import known_councils, locate_inputs
from .pipeline import build_combined, run_council, write_outputs
from .summary import summarise


def main():
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description="CGP recertification analysis (NISSA vs current beneficiaries).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--council", "-c", help="Council name as used in the file names, e.g. Telle")
    g.add_argument("--all", action="store_true", help="Run every council that has all three input files")
    g.add_argument("--list", action="store_true", help="List councils and which inputs are present")
    g.add_argument("--rewrite", action="store_true",
                   help="Rewrite every workbook and dashboard from saved results (after a layout change; no re-matching)")
    g.add_argument("--combined", action="store_true",
                   help="Rebuild only the combined all-councils analysis from councils already run")
    ap.add_argument("--data-dir", default=".", help="Folder that contains the three input folders (default: .)")
    ap.add_argument("--out-dir", default="output", help="Output folder (default: output)")
    ap.add_argument("--min-score", type=float, default=75.0, help="Minimum match score to accept a match (default 75)")
    ap.add_argument("--min-name", type=float, default=0.60, help="Minimum (strict-scaled) name similarity 0-1 to accept a match (default 0.60)")
    ap.add_argument("--review-score", type=float, default=55.0, help="Near-miss floor for the review queue (default 55)")
    args = ap.parse_args()

    base = Path(args.data_dir).resolve()
    out_root = (base / args.out_dir) if not Path(args.out_dir).is_absolute() else Path(args.out_dir)

    if args.list:
        print(f"{'Council':16s} NISSA  InProgram  PMT")
        for c in known_councils(base):
            p = locate_inputs(base, c)
            print(f"{c:16s} {'yes' if p['nissa'] else ' - ':5s}  {'yes' if p['inprogram'] else ' - ':9s}  {'yes' if p['pmt'] else ' - '}")
        return

    if args.combined:
        sys.exit(0 if build_combined(out_root) else 1)

    if args.rewrite:
        for c in sorted(p for p in out_root.glob(f"*/{CACHE_NAME}") if p.parent.name != COMBINED_NAME):
            with open(c, "rb") as fh:
                R = pickle.load(fh)
            print(f"\n=== {R['council']} === (results from {R['built']})")
            write_outputs(R, summarise(R), c.parent, R["council"])
        sys.exit(0 if build_combined(out_root) else 1)

    councils = known_councils(base) if args.all else [args.council]
    results = []
    for c in councils:
        try:
            s = run_council(base, out_root, c, args)
        except SystemExit as e:  # a data problem in one council should not stop the others
            print(f"   ! {c} FAILED: {e}")
            continue
        if s:
            results.append(s)
    if not results:
        sys.exit(1)
    if args.all:
        build_combined(out_root)
    else:
        print("   (run with --combined to refresh the all-councils analysis)")

"""Probabilistic matching of programme beneficiaries to NISSA members.

Household IDs differ between the two systems, so children are matched on first name,
surname (Jaro-Winkler + Soundex, swapped-name aware), date of birth, age and sex."""

from __future__ import annotations

import numpy as np
import pandas as pd
from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

from .cleaning import first_token, soundex
from .constants import CANDIDATE_MAX_AGE, COHERENCE_BONUS, WEIGHTS


class NameSim:
    """Cached Jaro-Winkler similarity, best over the tokens of multi-part names."""

    def __init__(self):
        """Start with an empty similarity cache."""
        self.cache: dict[tuple[str, str], float] = {}

    def __call__(self, a: str, b: str) -> float:
        """Similarity 0-1 of two names (NaN when either is empty)."""
        if not a or not b:
            return np.nan
        key = (a, b) if a <= b else (b, a)
        v = self.cache.get(key)
        if v is None:
            v = JaroWinkler.similarity(a, b)
            ta, tb = a.split(" "), b.split(" ")
            if len(ta) > 1 or len(tb) > 1:
                v = max(v, max(JaroWinkler.similarity(x, y) for x in ta for y in tb))
            self.cache[key] = v
        return v


def strict(s: float) -> float:
    """Rescale Jaro-Winkler so only close spellings score: 1.0->1, 0.9->0.75, 0.8->0.5, <=0.6->0."""
    return s if np.isnan(s) else min(1.0, max(0.0, (s - 0.6) / 0.4))


def dob_score(d1, d2) -> float:
    """Agreement 0-1 between two dates of birth, allowing for one-day shifts, day/month swaps and year typos (NaN when either is missing)."""
    if pd.isna(d1) or pd.isna(d2):
        return np.nan
    diff = abs((d1 - d2).days)
    if diff == 0:
        # 1 January is a common placeholder date of birth: an exact match on it is weak evidence
        return 0.7 if (d1.month == 1 and d1.day == 1) else 1.0
    if diff <= 1:
        return 0.95
    if d1.year == d2.year and d1.month == d2.day and d1.day == d2.month:
        return 0.85  # day/month transposed
    if d1.year == d2.year and d1.month == d2.month:
        return 0.6
    if diff <= 366:
        return 0.35
    if d1.month == d2.month and d1.day == d2.day and abs(d1.year - d2.year) == 1:
        return 0.5  # year typo
    return 0.0


def build_candidates(ben: pd.DataFrame, mem: pd.DataFrame) -> pd.DataFrame:
    """Blocking: a pair is scored if it shares a Soundex (straight or swapped) or a DOB."""
    cand_mem = mem[(mem["Age"].isna()) | (mem["Age"] <= CANDIDATE_MAX_AGE)].copy()
    cand_mem["sx_f"] = cand_mem["FirstName"].map(lambda n: soundex(first_token(n)))
    cand_mem["sx_s"] = cand_mem["Surname"].map(lambda n: soundex(first_token(n)))
    cand_mem["dob_k"] = cand_mem["DOB"].dt.strftime("%Y-%m-%d")

    b = ben.copy()
    b["sx_f"] = b["Prog_FirstName"].map(lambda n: soundex(first_token(n)))
    b["sx_s"] = b["Prog_Surname"].map(lambda n: soundex(first_token(n)))
    b["dob_k"] = b["Prog_DOB"].dt.strftime("%Y-%m-%d")

    keys_m = pd.concat([
        cand_mem[["midx", "sx_s"]].rename(columns={"sx_s": "k"}).assign(k=lambda d: "S" + d.k),
        cand_mem[["midx", "sx_f"]].rename(columns={"sx_f": "k"}).assign(k=lambda d: "F" + d.k),
        cand_mem[["midx", "dob_k"]].rename(columns={"dob_k": "k"}).assign(k=lambda d: "D" + d.k),
    ])
    keys_b = pd.concat([
        b[["bidx", "sx_s"]].rename(columns={"sx_s": "k"}).assign(k=lambda d: "S" + d.k),
        b[["bidx", "sx_f"]].rename(columns={"sx_f": "k"}).assign(k=lambda d: "F" + d.k),
        b[["bidx", "dob_k"]].rename(columns={"dob_k": "k"}).assign(k=lambda d: "D" + d.k),
        # swapped names: beneficiary first name vs member surname and vice versa
        b[["bidx", "sx_f"]].rename(columns={"sx_f": "k"}).assign(k=lambda d: "S" + d.k),
        b[["bidx", "sx_s"]].rename(columns={"sx_s": "k"}).assign(k=lambda d: "F" + d.k),
    ])
    keys_m = keys_m[keys_m["k"].str.len() > 1]
    keys_b = keys_b[keys_b["k"].str.len() > 1]
    pairs = keys_b.merge(keys_m, on="k")[["bidx", "midx"]].drop_duplicates()
    # date-of-birth +/- 1 day block (time-zone off-by-one safety net)
    for shift in (-1, 1):
        sb = b[["bidx", "Prog_DOB"]].dropna().copy()
        sb["k"] = (sb["Prog_DOB"] + pd.Timedelta(days=shift)).dt.strftime("%Y-%m-%d")
        p2 = sb.merge(cand_mem[["midx", "dob_k"]].rename(columns={"dob_k": "k"}), on="k")[["bidx", "midx"]]
        pairs = pd.concat([pairs, p2]).drop_duplicates()
    return pairs


def score_pairs(pairs: pd.DataFrame, ben: pd.DataFrame, mem: pd.DataFrame) -> pd.DataFrame:
    """Score every candidate (beneficiary, member) pair 0-100 from name, Soundex, date of birth, sex and age agreement."""
    sim = NameSim()
    B = ben.set_index("bidx")
    M = mem.set_index("midx")
    bf, bs, bd, ba, bx = (B["Prog_FirstName"], B["Prog_Surname"], B["Prog_DOB"], B["Prog_Age"], B["Prog_Sex"])
    mf, mo, ms, md, ma, mx = (M["FirstName"], M["OtherNames"], M["Surname"], M["DOB"], M["Age"], M["Sex"])

    rows = []
    for bi, mi in zip(pairs["bidx"].to_numpy(), pairs["midx"].to_numpy()):
        f1, s1 = bf[bi], bs[bi]
        f2, s2 = mf[mi], ms[mi]
        o2 = mo[mi]
        f2_all = f"{f2} {o2}".strip() if o2 else f2

        fs = strict(sim(f1, f2_all))
        ss = strict(sim(s1, s2))
        # a missing name part counts as no evidence (0), not as a free pass
        straight = np.mean([0.0 if np.isnan(fs) else fs, 0.0 if np.isnan(ss) else ss])
        a, b_ = strict(sim(f1, s2)), strict(sim(s1, f2_all))
        sw = np.mean([0.0 if np.isnan(a) else a, 0.0 if np.isnan(b_) else b_])
        full = strict(fuzz.token_sort_ratio(f"{f1} {s1}", f"{f2_all} {s2}") / 100.0)
        name = max(straight, sw, full)
        swapped = sw > straight + 0.05

        if swapped:
            ph = np.mean([soundex(first_token(f1)) == soundex(first_token(s2)),
                          soundex(first_token(s1)) == soundex(first_token(f2))])
        else:
            ph = np.mean([soundex(first_token(f1)) == soundex(first_token(f2)),
                          soundex(first_token(s1)) == soundex(first_token(s2))])

        dsc = dob_score(bd[bi], md[mi])
        a1, a2 = ba[bi], ma[mi]
        asc = np.nan if (pd.isna(a1) or pd.isna(a2)) else (1.0 if abs(a1 - a2) <= 1 else (0.5 if abs(a1 - a2) <= 2 else 0.0))
        x1, x2 = bx[bi], mx[mi]
        xsc = np.nan if (not x1 or not x2) else float(x1 == x2)

        comps = {"name": name, "phonetic": ph, "dob": dsc, "sex": xsc, "age": asc}
        num = sum(WEIGHTS[k] * v for k, v in comps.items() if not np.isnan(v))
        den = sum(WEIGHTS[k] for k, v in comps.items() if not np.isnan(v))
        total = 100.0 * num / den if den else 0.0
        # First name + exact (non-placeholder) date of birth is strong evidence even when the
        # surname differs (children often switch between the mother's and the father's surname).
        best_first = max(0.0 if np.isnan(fs) else fs, 0.0 if np.isnan(b_) else b_)
        fn_dob = (best_first >= 0.75) and (dsc >= 0.95)
        surname_differs = fn_dob and (max(0.0 if np.isnan(ss) else ss, 0.0 if np.isnan(a) else a) < 0.5)
        rows.append((bi, mi, total, name, fs, ss, ph, dsc, asc, xsc, swapped, fn_dob, surname_differs))

    return pd.DataFrame(rows, columns=["bidx", "midx", "score", "s_name", "s_first", "s_surname",
                                       "s_phonetic", "s_dob", "s_age", "s_sex", "names_swapped", "fn_dob",
                                       "surname_differs"])


def greedy_assign(scored: pd.DataFrame, col: str, min_score: float, min_name: float) -> pd.DataFrame:
    """One-to-one assignment, best score first."""
    s = scored[(scored[col] >= min_score) & ((scored["s_name"] >= min_name) | scored["fn_dob"])]
    s = s.sort_values(col, ascending=False)
    used_b, used_m, keep = set(), set(), []
    for row in s.itertuples(index=False):
        if row.bidx in used_b or row.midx in used_m:
            continue
        used_b.add(row.bidx)
        used_m.add(row.midx)
        keep.append(row)
    return pd.DataFrame(keep, columns=s.columns)


def match_beneficiaries(ben, mem, min_score, review_score, min_name):
    """Match beneficiaries to NISSA members.

    Returns (final one-to-one matches, best rejected candidate per unmatched beneficiary,
    all scored pairs, duplicate programme records). A second pass gives a coherence
    bonus to candidates in the NISSA household most siblings matched into."""
    pairs = build_candidates(ben, mem)
    print(f"   candidate pairs after blocking: {len(pairs):,}")
    scored = score_pairs(pairs, ben, mem)
    scored = scored.merge(mem[["midx", "HouseholdId"]], on="midx", how="left")
    scored = scored.merge(ben[["bidx", "Prog_HouseholdId"]], on="bidx", how="left")

    # Pass 1: plain one-to-one
    p1 = greedy_assign(scored, "score", min_score, min_name)
    # Household coherence: the NISSA household most siblings landed in becomes the anchor
    anchor = (p1.groupby(["Prog_HouseholdId", "HouseholdId"]).size().rename("n").reset_index()
              .sort_values("n", ascending=False).drop_duplicates("Prog_HouseholdId"))
    anchor = anchor[anchor["n"] >= 1][["Prog_HouseholdId", "HouseholdId"]].assign(in_anchor=True)
    scored = scored.merge(anchor, on=["Prog_HouseholdId", "HouseholdId"], how="left")
    scored["in_anchor"] = scored["in_anchor"].fillna(False).astype(bool)
    scored["final_score"] = np.minimum(100.0, scored["score"] + np.where(scored["in_anchor"], COHERENCE_BONUS, 0.0))

    # Pass 2: assignment on coherence-adjusted score
    final = greedy_assign(scored, "final_score", min_score, min_name)

    # Duplicate programme records: an unmatched beneficiary whose acceptable candidate was
    # already claimed by another beneficiary is the same child listed twice.
    matched_b = set(final["bidx"])
    owner = dict(zip(final["midx"], final["bidx"]))
    dup = (scored[~scored["bidx"].isin(matched_b) & scored["midx"].isin(owner.keys())
                  & (scored["final_score"] >= min_score) & ((scored["s_name"] >= min_name) | scored["fn_dob"])]
           .sort_values("final_score", ascending=False).drop_duplicates("bidx"))
    dup = dup.assign(dup_of_bidx=dup["midx"].map(owner))[["bidx", "dup_of_bidx", "final_score"]]

    # Best rejected candidate per unmatched beneficiary (for the review queue)
    near = (scored[~scored["bidx"].isin(matched_b) & (scored["final_score"] >= review_score)]
            .sort_values("final_score", ascending=False).drop_duplicates("bidx"))
    return final, near, scored, dup


def match_result(score: float, min_score: float, review_score: float) -> str:
    """Match level of a score: Matched, High Match, Moderate Match, Low Match or No Match."""
    if pd.isna(score) or score < review_score:
        return "No Match"
    if score >= 95:
        return "Matched"
    if score >= 85:
        return "High Match"
    if score >= min_score:
        return "Moderate Match"
    return "Low Match"

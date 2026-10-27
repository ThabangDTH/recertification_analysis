"""Cleaning helpers: names, labels, dates of birth, ages, sex and CBC classes."""

from __future__ import annotations

from datetime import date

import jellyfish
import numpy as np
import pandas as pd

from .constants import LOCAL_TZ_OFFSET, MISSING_TOKENS


def clean_text(s: pd.Series) -> pd.Series:
    """Upper-case, strip, letters/spaces only; NISSA missing tokens -> ''."""
    s = s.astype("string").fillna("").str.upper().str.strip()
    s = s.where(~s.isin(MISSING_TOKENS), "")
    s = s.str.replace(r"[^A-Z ]", " ", regex=True).str.replace(r"\s+", " ", regex=True).str.strip()
    return s.astype(object)


def clean_label(s: pd.Series) -> pd.Series:
    """Strip a text column and turn NISSA missing tokens into ''; keeps the original case."""
    s = s.astype("string").fillna("").str.strip()
    return s.where(~s.str.upper().isin(MISSING_TOKENS), "").astype(object)


def parse_dob(s: pd.Series) -> pd.Series:
    """Parse '2010-05-16T22:00:00.000Z' / '2013-06-15 22:00:00.0000000' to a local calendar date.

    Both sources store midnight-local as 22:00 UTC the previous day, so we add 2h before
    truncating. Midnight values are unaffected."""
    raw = s.astype("string").fillna("").str.strip()
    raw = raw.where(~raw.str.upper().isin(MISSING_TOKENS), "")
    raw = raw.str.replace("T", " ", regex=False).str.slice(0, 19)
    dt = pd.to_datetime(raw, errors="coerce", format="mixed")
    dt = (dt + LOCAL_TZ_OFFSET).dt.normalize()
    dt = dt.where((dt.dt.year >= 1900) & (dt.dt.year <= date.today().year))
    return dt


def to_age(s: pd.Series) -> pd.Series:
    """Convert an age column to numbers; anything non-numeric or outside 0-120 becomes NaN."""
    a = pd.to_numeric(s, errors="coerce")
    return a.where((a >= 0) & (a <= 120))


def age_at(dob: pd.Series, ref: pd.Series | pd.Timestamp) -> pd.Series:
    """Whole years between each date of birth and the reference date(s)."""
    ref = pd.to_datetime(ref)
    years = (ref - dob).dt.days / 365.25
    return np.floor(years)


def normalise_sex(s: pd.Series) -> pd.Series:
    """Map free-text sex values to 'Male', 'Female' or '' (unknown)."""
    s = s.astype("string").fillna("").str.strip().str.upper()
    return s.map(lambda v: "Male" if v.startswith("M") else ("Female" if v.startswith("F") else "")).astype(object)


def normalise_cbc(s: pd.Series) -> pd.Series:
    """Map the many CBC spellings (e.g. 'Middle (Ea mahareng)', 'Middle (Mahareng)') to Ultra-Poor / Poor / Middle / Able / Unclassified."""
    def one(v):
        """Classify a single CBC label by keyword."""
        v = str(v).lower() if pd.notna(v) else ""
        if "ultra" in v or "mohloki-hloki" in v or "hloki-hloki" in v:
            return "Ultra-Poor"
        if "poor" in v or "mohloki" in v:
            return "Poor"
        if "middle" in v or "mahareng" in v:
            return "Middle"
        if "able" in v or "khonang" in v:
            return "Able"
        return "Unclassified"
    return s.map(one)


def soundex(name: str) -> str:
    """Soundex code of a name ('' for an empty name)."""
    return jellyfish.soundex(name) if name else ""


def first_token(name: str) -> str:
    """First word of a name ('' for an empty name)."""
    return name.split(" ")[0] if name else ""

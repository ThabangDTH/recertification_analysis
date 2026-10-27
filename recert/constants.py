"""All settings and fixed labels in one place: input folders, CBC classes, matching weights,
outcome and flag labels, community-validation results and the plain-language wording used
in the workbooks and dashboards."""

from __future__ import annotations

import pandas as pd


# Input folders and sheets ------------------------------------------------------------------------
NISSA_DIR = "NISSA Data Extracts"
INPROGRAM_DIR = "InProgram"
PMT_DIR = "PMT Scores"
PMT_SHEET = "PMT_Results"
OLD_NISSA_DIR = "Old NISSA Data Extracts"  # baseline households and their poverty status before the new NISSA

# Programmes --------------------------------------------------------------------------------------
# CGP  (Child Grant Programme): children 0-17 in Poor/Ultra-Poor households
# PA   (Public Assistance): Poor/Ultra-Poor households with no member aged 0-17
# OVC-B (Orphans and Vulnerable Children Bursary): children 12-17 in Poor/Ultra-Poor households
CHILD_MAX_AGE = 17
OVCB_MIN_AGE = 12
OVCB_MAX_AGE = 17

# Data cleaning -----------------------------------------------------------------------------------
MISSING_TOKENS = {"", "NULL", "NAN", "NONE", "NAT", "NOT SET", "9998 NO VALUE", "9999", "UNKNOWN"}
LOCAL_TZ_OFFSET = pd.Timedelta(hours=2)  # Lesotho is UTC+2; source DOBs are stored at 22:00 UTC

# Community-based classification (CBC) ------------------------------------------------------------
CBC_ORDER = ["Ultra-Poor", "Poor", "Middle", "Able"]
CBC_FULL = {
    "Ultra-Poor": "Ultra-Poor (Mohloki-hloki)",
    "Poor": "Poor (Mohloki)",
    "Middle": "Middle (Ea Mahareng)",
    "Able": "Able (Ea Khonang)",
    "Unclassified": "Unclassified",
}
POOR_CLASSES = {"Ultra-Poor", "Poor"}

# Proper district names, keyed by their letters only (extracts spell them "Mohales Hoek", "Mohale´S Hoek", ...)
DISTRICT_NAMES = {"mohaleshoek": "Mohale's Hoek", "qachasnek": "Qacha's Nek", "thabatseka": "Thaba-Tseka",
                  "leribe": "Leribe", "quthing": "Quthing", "maseru": "Maseru", "berea": "Berea",
                  "mafeteng": "Mafeteng", "mokhotlong": "Mokhotlong", "buthabuthe": "Butha-Buthe"}
EXITED_CLASSIFICATIONS = {"member moved out", "member has passed away", "data collection error"}

# Matching ----------------------------------------------------------------------------------------
# Match-score weights (renormalised over the components that are available for a pair)
WEIGHTS = {"name": 45.0, "phonetic": 10.0, "dob": 30.0, "sex": 10.0, "age": 5.0}
COHERENCE_BONUS = 5.0  # added to candidates inside the household most siblings matched to
CANDIDATE_MAX_AGE = 25  # NISSA members older than this are never beneficiary candidates

# Outcomes for children already in the programme --------------------------------------------------
OUTCOME_REMAIN = "Remain"
OUTCOME_NEW = "Proposed new entrant"
EXIT_NOT_POOR = "Exit - household no longer Poor/Ultra-Poor"
EXIT_AGED_OUT = "Exit - aged out (18+)"
EXIT_MOVED = "Exit - moved out"
EXIT_DECEASED = "Exit - passed away"
EXIT_DATA_ERR = "Exit - removed as data-collection error"
EXIT_DUPLICATE = "Exit - duplicate programme record"
# Not finding a child in NISSA is not a reason to exit: these children are flagged for investigation
FLAG_LOW = "Flag - only a low match in NISSA"
FLAG_NONE = "Flag - not found in NISSA"
FLAG_NO_HH = "Flag - household missing from NISSA household list"
OUTCOME_ORDER = [OUTCOME_REMAIN, EXIT_NOT_POOR, EXIT_AGED_OUT, EXIT_MOVED, EXIT_DECEASED,
                 EXIT_DATA_ERR, EXIT_DUPLICATE, FLAG_LOW, FLAG_NONE, FLAG_NO_HH, OUTCOME_NEW]

# Match result levels -----------------------------------------------------------------------------
# Match result levels (score 0-100). Low Match = closest NISSA record scored between
# --review-score and --min-score, so it was not accepted.
MATCH_LEVELS = ["Matched", "High Match", "Moderate Match", "Low Match", "No Match"]

# NISSA columns read ------------------------------------------------------------------------------
HH_COLS = ["HouseholdId", "PackageEvent_OrgUnitName_CC", "PackageEvent_OrgUnitName_District",
           "Original_VillageName", "System Listing_Village Name", "Updated HouseholdHead", "Updated CBC",
           "Original_CommunityClassification", "CollectionStatusDate"]
MEM_COLS = ["HouseholdId", "HouseholdMemberId", "HouseholdMember_Status",
            "System Collection_Household Member Classification",
            "Original_FirstName", "Original_Surname", "Original_DateOfBirth", "Original_Gender",
            "Household Roster_Member First name", "Household Roster_Member Other names",
            "Household Roster_Member Surname", "Household Roster_Date of Birth",
            "Household Roster_Age in Years", "Household Roster_Sex", "Household Roster_Relationship"]

# Community validation ----------------------------------------------------------------------------
CV_DIR = "Community Validation"
CV_REQUIRED = ["Select Community Council", "Enter Household ID", "CV Outcome", "Select the corrected categorization"]
CV_NAME_MIN = 80  # head-name similarity (0-100) needed to apply a correction
CV_CHANGED = "CBC changed"
CV_CONFIRMED = "No change - confirmed"
CV_ALREADY = "Already the same in NISSA (CV said changed)"
CV_DIFFERS = "No change in CV - NISSA CBC differs (NISSA kept)"
CV_NOT_FOUND = "Not applied - household not in NISSA extract"
CV_NAME_DIFF = "Not applied - head name differs"
CV_ORDER = [CV_CHANGED, CV_CONFIRMED, CV_ALREADY, CV_DIFFERS, CV_NOT_FOUND, CV_NAME_DIFF]

# Plain-language labels used in the workbook and dashboard ----------------------------------------
STATUS_REMAINING = "Remaining in programme"
STATUS_NEW = "Proposed new entrant"
# outcome -> (plain reason, action)
PLAIN_EXIT = {
    EXIT_NOT_POOR: ("Household is no longer Poor or Ultra-Poor", "Exit"),
    EXIT_AGED_OUT: ("Child is now 18 or older", "Exit"),
    EXIT_MOVED: ("Child has moved out of the household", "Exit"),
    EXIT_DECEASED: ("Child has passed away", "Exit"),
    EXIT_DATA_ERR: ("Child was a data-collection error", "Exit"),
    EXIT_DUPLICATE: ("Child is listed twice in the programme", "Remove the duplicate record"),
}
PLAIN_FLAG = {
    FLAG_LOW: ("Only a low match found in NISSA", "Check the suggested NISSA record - do not exit"),
    FLAG_NONE: ("Not found in NISSA data", "Investigate in the field - do not exit"),
    FLAG_NO_HH: ("Household missing from the NISSA household list (no CBC)", "Check the household's CBC - do not exit"),
}
# Suggestion shown with each match result (on the chart and in the sheets)
MATCH_SUGGESTION = {
    "Matched": "no action needed",
    "High Match": "no action needed",
    "Moderate Match": "spot-check if possible",
    "Low Match": "check suggested record",
    "No Match": "investigate in the field",
}

# Saved results and the combined analysis ---------------------------------------------------------
CACHE_NAME = "_results_cache.pkl"  # per-council results, reused to build the combined analysis
COMBINED_NAME = "All_Councils"
COMBINED_TITLE = "All Community Councils"

"""
CGP Recertification Analysis
============================

For one community council (or all of them) this script:

  1. Reads the NISSA extract (EnumeratedHouseholds + EnumeratedHouseholdMembers).
  2. Applies community validation: where a household's CV Outcome is "CBC Changed", its
     Updated CBC becomes the corrected categorization (matched on household ID, head name checked).
  3. Flags Poor / Ultra-Poor households using the Updated CBC and finds Child Grant Programme (CGP)
     eligible children: active members (HouseholdMember_Status == 1) aged 17 and below.
  4. Ties every household to its PMT score (PMT Scores/Output_<Council>.xlsx, sheet PMT_Results).
  5. Matches the current beneficiary list (InProgram/<Council>.xlsx) to NISSA members. Household IDs
     differ between the two systems, so matching is probabilistic on first name, surname
     (Jaro-Winkler + Soundex, swapped-name aware), date of birth, age and sex, with a
     household-coherence pass. Each beneficiary gets a 0-100 match score and a match result.
  6. Decides, for every child already in the programme, Remain / Exit (with reason) / Flagged for
     investigation (low or no match - never exited automatically), and lists new entrants.
  7. Writes, per council, into output/<Council>/:
       Recertification_<Council>.xlsx - Summary, CommunityValidation, PoorHouseholds, EligibleHouseholds,
           EligibleChildren, AlreadyInProgram, RemainingInProgram, ExitingProgram,
           FlaggedForInvestigation, NewEntrants
       Dashboard_<Council>.html       - one-page summary (tiles, key findings, bar charts + tables)
     and the same for all councils together in output/All_Councils/.

Code layout (package ``recert``)
--------------------------------
    constants.py           every setting and label (folders, CBC classes, weights, outcomes, wording)
    cleaning.py            names, dates of birth, ages, sex and CBC normalisation
    inputs.py              finding and loading the NISSA, InProgram and PMT files
    validation.py          community validation corrections to the Updated CBC
    matching.py            beneficiary-to-NISSA matching
    analysis.py            eligibility and Remain / Exit / Flag / New entrant decisions for one council
    summary.py             headline figures
    tables.py              the stakeholder tables
    excel_report.py        the Excel workbook
    dashboard.py           the HTML dashboard (its template is in dashboard_template.py)
    formatting.py          small text-formatting helpers
    pipeline.py            running councils, caching results, the combined analysis
    cli.py                 command-line options

Usage
-----
    python recertify.py --council Telle       # one council
    python recertify.py --all                 # every council with all three input files + combined analysis
    python recertify.py --combined            # rebuild only the combined analysis from councils already run
    python recertify.py --rewrite             # rewrite all workbooks/dashboards from saved results
    python recertify.py --list                # show which councils are ready to run
"""

from recert.cli import main

if __name__ == "__main__":
    main()

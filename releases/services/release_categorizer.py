"""Keyword-based classification of a release note line into a ReleaseCategory.

Shared by the seed builder (commit subjects / Jira summaries) and the Word upload
parser (for lines that sit outside a "New / Fixed / Improved / Security" heading).
"""
import re

_RULES = [
    ("SECURITY", r"snyk|vulnerab|security|xss|csrf|injection|authori[sz]|authenticat|\bsso\b|password|encrypt|sonar|owasp|cve-"),
    ("BUG_FIX", r"\bfix|\bbug|issue|error|not working|not seen|missing|not being|not receiv|not display|not show|defect|incorrect|wrong|duplicate|\bsl1\b|production|revert|broken|fail|crash|stop|empty|problem|\bnot\b"),
    ("NEW_FEATURE", r"implement|\bnew\b|creat|\badd|support|integrat|\bapi\b|report|template|enabl|introduc|\bseed|portal|screen|tab\b|feature|setup|picker"),
]


def categorize(text: str) -> str:
    lowered = text.lower()
    for category, pattern in _RULES:
        if re.search(pattern, lowered):
            return category
    return "IMPROVEMENT"

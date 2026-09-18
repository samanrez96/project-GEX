"""Shared plain-text normalization for identifier-like CharFields
(national ID, medical system number, clinic phone, ...).

Reuses common.dates.normalize_digits (the project's existing Persian/Arabic
-> ASCII digit converter) so this stays the single normalization helper for
non-date identifier fields, instead of duplicating digit-translation logic.
"""

from common.dates import normalize_digits


def normalize_identifier(value):
    """Trim whitespace and convert Persian/Arabic digits to ASCII.

    Preserves leading zeros and all non-digit characters (+, -, spaces,
    parentheses). Never casts to int. Returns '' for falsy input.
    """
    if not value:
        return ''
    return normalize_digits(value).strip()

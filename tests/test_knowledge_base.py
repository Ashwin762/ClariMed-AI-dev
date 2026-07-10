"""
tests/test_knowledge_base.py

Integrity of the authored medical knowledge base.

These catch the kind of content bug that silently degrades the product:
a duplicate ID (which ChromaDB rejects at seed time), a condition with no
keywords (which can therefore never match a symptom), or a condition in the
scoring engine that has no corresponding knowledge base document.
"""

import pytest

from ai.rag.kb_loader import load_all_docs, get_section
from ai.rules.condition_engine import RISK_BASE, IMAGE_SCORERS, BODY_PART_SYMPTOMS


DOCS = load_all_docs()
DOC_IDS = [d["id"] for d in DOCS]


def test_knowledge_base_is_not_empty():
    assert len(DOCS) > 0, "no knowledge base documents were loaded"


def test_no_duplicate_condition_ids():
    """A duplicate ID makes kb_initializer fail with DuplicateIDError, and
    means one document silently shadows another."""
    dupes = {i for i in DOC_IDS if DOC_IDS.count(i) > 1}
    assert not dupes, f"duplicate condition IDs found: {sorted(dupes)}"


def test_every_document_has_required_frontmatter():
    for d in DOCS:
        assert d["id"], f"{d['source_path']}: missing id"
        assert d["disease_name"], f"{d['id']}: missing disease_name"
        assert d["body_part"], f"{d['id']}: missing body_part"
        assert d["specialist"], f"{d['id']}: missing specialist"
        assert isinstance(d["emergency_possible"], bool), f"{d['id']}: emergency_possible must be bool"


def test_every_document_has_keywords():
    """A condition with no keywords can never match any reported symptom.
    It would sit in the knowledge base, unreachable."""
    for d in DOCS:
        assert d["keywords"], f"{d['id']} ({d['disease_name']}) has no keywords — it can never match"


def test_every_document_has_an_overview_section():
    """The offline structured fallback reads Overview. Missing it degrades
    guidance silently, with no error."""
    for d in DOCS:
        overview = get_section(d, "Overview")
        assert overview.strip(), f"{d['id']} has no Overview section"


def test_every_document_has_a_disclaimer():
    """Medical disclaimer must be present on every condition."""
    for d in DOCS:
        text = d["full_text"].lower()
        assert "disclaimer" in text, f"{d['id']} has no medical disclaimer"


def test_every_body_part_in_symptoms_has_at_least_one_condition():
    """A body part offered in the UI with no conditions behind it always
    returns out_of_coverage — a dead end for the user."""
    covered = {d["body_part"] for d in DOCS}
    for bp in BODY_PART_SYMPTOMS:
        assert bp in covered, f"body part '{bp}' is offered in the UI but has no conditions"


def test_every_condition_has_a_risk_baseline():
    """A condition missing from RISK_BASE silently defaults to 'yellow'."""
    for d in DOCS:
        assert d["id"] in RISK_BASE, f"{d['id']} ({d['disease_name']}) has no RISK_BASE entry"


def test_no_orphaned_risk_baselines():
    """A RISK_BASE entry with no matching document means a stale reference."""
    for cid in RISK_BASE:
        assert cid in DOC_IDS, f"RISK_BASE has entry '{cid}' with no knowledge base document"


def test_no_orphaned_image_scorers():
    """An image scorer for a condition that doesn't exist is dead code, and
    signals a rename that wasn't propagated."""
    for cid in IMAGE_SCORERS:
        assert cid in DOC_IDS, f"IMAGE_SCORERS has entry '{cid}' with no knowledge base document"


def test_risk_baselines_use_valid_levels():
    for cid, level in RISK_BASE.items():
        assert level in ("green", "yellow", "red"), f"{cid} has invalid risk level '{level}'"


def test_specialists_are_recognised():
    """Every KB specialist must exist in the router's closed list, otherwise
    the specialist directory lookup returns an empty list."""
    from ai.rag.specialist_router import SPECIALIST_TYPES
    for d in DOCS:
        # Some KB entries phrase it as "Dentist (or General Physician ...)"
        primary = d["specialist"].split("(")[0].strip()
        assert any(primary.startswith(s) or s in primary for s in SPECIALIST_TYPES), (
            f"{d['id']} lists specialist '{d['specialist']}' which is not in SPECIALIST_TYPES"
        )
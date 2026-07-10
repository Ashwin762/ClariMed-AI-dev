"""
tests/conftest.py

Shared fixtures. Deliberately dependency-light: the safety-critical tests
must run without ChromaDB, without FastAPI, and without an LLM key, so a
regression in the safety logic can always be caught — even on a machine
with nothing installed and no internet.
"""

import pytest

# Feature dicts matching the exact shape returned by
# ai/vision/image_analysis.py::extract_features
NEUTRAL_FEATURES = {
    "redness": 0.0, "yellowness": 0.0, "whiteness": 0.0,
    "variance": 0.0, "brightness": 128.0, "sharpness": 10.0,
}

RED_FEATURES = {
    "redness": 0.85, "yellowness": 0.1, "whiteness": 0.05,
    "variance": 0.3, "brightness": 150.0, "sharpness": 12.0,
}

YELLOW_NAIL_FEATURES = {
    "redness": 0.05, "yellowness": 0.9, "whiteness": 0.1,
    "variance": 0.4, "brightness": 150.0, "sharpness": 12.0,
}


@pytest.fixture
def neutral_features():
    return dict(NEUTRAL_FEATURES)


@pytest.fixture
def red_features():
    return dict(RED_FEATURES)


@pytest.fixture
def yellow_nail_features():
    return dict(YELLOW_NAIL_FEATURES)
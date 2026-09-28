"""Filters on GET /api/issues, against the known sample set in conftest.py."""

import pytest


def list_call_ids(client, query: str) -> list[str]:
    response = client.get(f"/api/issues?{query}")
    assert response.status_code == 200
    return [item["call_id"] for item in response.json()["items"]]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("clinic=Clinic Alpha", ["call-0002", "call-0001", "call-0000"]),
        ("clinic=Clinic Gamma", ["call-0007", "call-0006"]),
        ("category=booking", ["call-0007", "call-0003", "call-0001", "call-0000"]),
        ("category=patient_identification", []),
        (
            "status=open",
            ["call-0007", "call-0006", "call-0005", "call-0003", "call-0002", "call-0000"],
        ),
        ("status=resolved", ["call-0004", "call-0001"]),
        ("severity=medium", ["call-0007", "call-0004", "call-0002"]),
        ("severity=critical", ["call-0003"]),
    ],
)
def test_single_filter(client, sample_issues, query, expected):
    assert list_call_ids(client, query) == expected


def test_combined_filters_use_and(client, sample_issues):
    query = "clinic=Clinic Alpha&category=booking&status=open"
    assert list_call_ids(client, query) == ["call-0000"]

    query = "category=booking&status=open"
    assert list_call_ids(client, query) == ["call-0007", "call-0003", "call-0000"]

    query = "clinic=Clinic Beta&category=booking&status=open&severity=critical"
    assert list_call_ids(client, query) == ["call-0003"]

    query = "clinic=Clinic Gamma&category=technical"
    assert list_call_ids(client, query) == []


def test_clinic_filter_ignores_case_and_spacing(client, sample_issues):
    assert list_call_ids(client, "clinic=  clinic   ALPHA ") == [
        "call-0002",
        "call-0001",
        "call-0000",
    ]


def test_empty_filter_values_mean_no_filter(client, sample_issues):
    response = client.get("/api/issues?clinic=&category=&status=&severity=")

    assert response.json()["total"] == 8


def test_unknown_clinic_returns_no_issues(client, sample_issues):
    assert list_call_ids(client, "clinic=Nowhere") == []


@pytest.mark.parametrize("query", ["category=billing", "status=closed", "severity=urgent"])
def test_invalid_filter_value_returns_422(client, sample_issues, query):
    assert client.get(f"/api/issues?{query}").status_code == 422


def test_total_counts_all_matches_not_just_the_page(client, sample_issues):
    body = client.get("/api/issues?status=open").json()

    assert body["total"] == 6
    assert body["pages"] == 1

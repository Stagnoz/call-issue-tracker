"""Extra 5: free-text search on the description and the call_id."""

import pytest

from tests.conftest import make_issue


@pytest.fixture
def searchable(session):
    make_issue(session, call_id="call-a1", description="Assistant booked a Sunday visit.")
    make_issue(session, call_id="call-b2", description="Transfer to the FRONT DESK failed.")
    make_issue(session, call_id="call-sunday-3", description="Hold music restarted.")
    make_issue(session, call_id="call-c4", description="Discount of 50% quoted by mistake.")
    make_issue(session, call_id="call_d5", description="Wrong opening hours given.", severity="low")


def call_ids(client, query: str) -> list[str]:
    response = client.get(f"/api/issues?{query}")
    assert response.status_code == 200
    return sorted(item["call_id"] for item in response.json()["items"])


def test_search_matches_description_case_insensitively(client, searchable):
    assert call_ids(client, "q=front desk") == ["call-b2"]


def test_search_matches_description_and_call_id(client, searchable):
    assert call_ids(client, "q=SUNDAY") == ["call-a1", "call-sunday-3"]


def test_search_combines_with_other_filters(client, searchable):
    assert call_ids(client, "q=call&severity=low") == ["call_d5"]


def test_percent_and_underscore_are_literal(client, searchable):
    assert call_ids(client, "q=50%25") == ["call-c4"]
    assert call_ids(client, "q=call_") == ["call_d5"]


def test_empty_search_is_ignored(client, searchable):
    assert client.get("/api/issues?q=%20%20").json()["total"] == 5


def test_search_longer_than_100_characters_is_rejected(client):
    assert client.get("/api/issues", params={"q": "x" * 101}).status_code == 422


def test_search_box_keeps_the_query_and_links_carry_it(client, session):
    for index in range(30):
        make_issue(session, call_id=f"call-{index}", description="Assistant misheard the date.")

    text = client.get("/issues?q=misheard").text

    assert 'name="q" type="search" value="misheard"' in text
    assert "30 issues matching these filters" in text
    assert 'href="/issues?q=misheard&amp;page=2"' in text
    assert '<input type="hidden" name="return_query" value="q=misheard">' in text


def test_search_with_no_match_shows_empty_state(client, searchable):
    assert "No issues match these filters." in client.get("/issues?q=nothing-like-this").text

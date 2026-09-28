"""GET /api/stats against the known sample set in conftest.py."""


def test_stats_on_known_sample_set(client, sample_issues):
    stats = client.get("/api/stats").json()

    assert stats["total"] == 8
    assert stats["open"] == 6
    assert stats["resolved"] == 2
    # All six categories, count descending, ties alphabetical by label.
    assert [(row["category"], row["count"]) for row in stats["by_category"]] == [
        ("booking", 4),
        ("information", 2),
        ("forwarding", 1),
        ("technical", 1),
        ("other", 0),
        ("patient_identification", 0),
    ]
    assert stats["by_category"][-1]["label"] == "Patient identification"
    # Alpha and Beta each have one resolved issue.
    assert stats["by_clinic"] == [
        {"clinic": "Clinic Alpha", "count": 3, "open": 2},
        {"clinic": "Clinic Beta", "count": 3, "open": 2},
        {"clinic": "Clinic Gamma", "count": 2, "open": 2},
    ]
    assert [row["open"] for row in stats["by_category"]] == [3, 2, 0, 1, 0, 0]


def test_stats_on_empty_database(client):
    stats = client.get("/api/stats").json()

    assert (stats["total"], stats["open"], stats["resolved"]) == (0, 0, 0)
    assert len(stats["by_category"]) == 6
    assert all(row["count"] == 0 for row in stats["by_category"])
    assert stats["by_clinic"] == []


def test_resolving_updates_open_count(client, sample_issues):
    client.post(f"/api/issues/{sample_issues[0].id}/resolve")

    stats = client.get("/api/stats").json()
    assert (stats["total"], stats["open"], stats["resolved"]) == (8, 5, 3)

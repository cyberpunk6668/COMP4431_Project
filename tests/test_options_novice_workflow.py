"""API regressions for plain explanations use synthetic quotes and no model calls."""
import pytest

from test_options_collective_workflow import SequenceGateway
from test_options_workflow import make_client


def activity(brief):
    return next(card for card in brief["cards"] if card["id"] == "activity")


class ChangedFieldsGateway(SequenceGateway):
    def __init__(self, change):
        super().__init__()
        self.change = change

    async def snapshot(self, *args):
        result = await super().snapshot(*args)
        self.change(result)
        return result


def fail_cloud(service):
    async def unexpected(*args, **kwargs):
        raise AssertionError("Plain language reports should not need a model request")
    service.llm.complete = unexpected


def test_plain_brief_is_available_without_model_and_keeps_delayed_label(tmp_path):
    client, service = make_client(tmp_path, SequenceGateway(mode=3))
    fail_cloud(service)
    data = client.post("/api/options/analyze", json={"symbol": "AAPL", "language": "zh"}).json()
    brief = data["plain_brief"]
    assert brief["headline"] and brief["cards"] and brief["next_steps"]
    assert brief["scope"]["symbol"] == "AAPL"
    assert "延迟" in brief["freshness"]["label"]
    assert data["interpretation"]["status"] == "skipped"
    visual = activity(brief).get("visual")
    assert visual and "人" not in activity(brief)["answer"]
    assert "合约" in activity(brief)["answer"]


@pytest.mark.parametrize("value", [0, None])
def test_zero_or_missing_activity_does_not_create_a_balanced_market_picture(tmp_path, value):
    def change(snapshot):
        for quote in snapshot["quotes"]:
            quote["volume"] = value
            if value is None:
                quote["volume_received_at"] = None

    client, service = make_client(tmp_path, ChangedFieldsGateway(change))
    fail_cloud(service)
    data = client.post("/api/options/analyze", json={"symbol": "AAPL"}).json()
    card = activity(data["plain_brief"])
    assert not card.get("visual")
    assert "各半" not in card["answer"] and "50" not in card["answer"]
    assert data["metrics"]["put_call_volume"]["value"] is None


def test_missing_and_zero_activity_have_different_plain_explanations(tmp_path):
    explanations = []
    for index, value in enumerate((0, None)):
        def change(snapshot, value=value):
            for quote in snapshot["quotes"]:
                quote["volume"] = value
                if value is None:
                    quote["volume_received_at"] = None

        target = tmp_path / str(index)
        target.mkdir()
        client, _ = make_client(target, ChangedFieldsGateway(change))
        data = client.post("/api/options/analyze", json={"symbol": "AAPL"}).json()
        explanations.append(activity(data["plain_brief"])["answer"])
    assert explanations[0] != explanations[1]


def test_batch_brief_preserves_success_scope_and_reports_partial_failure(tmp_path):
    client, service = make_client(tmp_path, SequenceGateway(mode=3, fail_symbols={"FAIL"}))
    fail_cloud(service)
    response = client.post("/api/options/batch", json={
        "items": [{"symbol": "AAPL"}, {"symbol": "MSFT"}, {"symbol": "FAIL"}], "language": "zh",
    })
    assert response.status_code == 200
    data = response.json()
    brief = data["plain_brief"]
    assert len(data["failures"]) == 1
    assert len(brief["items"]) == 2
    assert brief["items"][0]["symbol"] == "AAPL"
    assert brief["status"] == "limited"
    assert data["reports"][0]["plain_brief"]["scope"]["symbol"] == "AAPL"


def test_empty_batch_capture_is_explained_as_limited_evidence(tmp_path):
    client, _ = make_client(tmp_path, SequenceGateway(fail_symbols={"FAIL"}))
    data = client.post("/api/options/batch", json={"items": [{"symbol": "FAIL"}]}).json()
    assert not data["reports"]
    assert data["plain_brief"]["status"] == "limited"
    assert not data["plain_brief"]["items"]


def test_plain_evidence_resolves_to_the_same_single_snapshot(tmp_path):
    client, _ = make_client(tmp_path, SequenceGateway())
    data = client.post("/api/options/analyze", json={"symbol": "AAPL"}).json()
    allowed = {"g0." + record["id"] for record in data["collective"]["evidence"]}
    references = set(data["plain_brief"]["evidence_ids"])
    for card in data["plain_brief"]["cards"]:
        references.update(card["evidence_ids"])
    assert references and references <= allowed


def test_english_brief_uses_requested_language(tmp_path):
    client, _ = make_client(tmp_path, SequenceGateway(mode=3))
    data = client.post("/api/options/analyze", json={"symbol": "AAPL", "language": "en"}).json()
    brief = data["plain_brief"]
    assert "delay" in brief["freshness"]["label"].lower()
    assert all(not any("\u4e00" <= char <= "\u9fff" for char in card["question"] + card["answer"]) for card in brief["cards"])

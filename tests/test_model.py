"""Provider requests are mocked; request timing and terminal guards stay offline."""

import pytest
from smolagents import OpenAIModel
from smolagents.models import ChatMessage

from chem_agent.config import Settings
from chem_agent.model import ModelUnavailable, TracedModel
from chem_agent.trace import RunTrace


@pytest.fixture
def model(tmp_path):
    settings = Settings(root=tmp_path, api_key="offline-dummy-key")
    trace = RunTrace(tmp_path / "runs", "离线模型测试", {}, "test", (settings.api_key,))
    instance = TracedModel(settings, trace)
    yield instance
    instance.client.close()


def test_successful_request_records_completion_time_and_latency(model, monkeypatch):
    clock = iter([10.0, 10.125])
    monkeypatch.setattr("chem_agent.model.perf_counter", lambda: next(clock))

    def provider_response(_model, *_args, **_kwargs):
        model.trace.data["model_requests"].append({"status": "pending"})
        return ChatMessage(role="assistant", content="离线答复")

    monkeypatch.setattr(OpenAIModel, "generate", provider_response)
    model.generate([])
    entry = model.trace.data["model_requests"][-1]
    assert entry["status"] == "succeeded"
    assert entry["latency_ms"] == 125
    assert entry["finished_at"]


@pytest.mark.parametrize("status_code", [401, 403, 402, 429, 500])
def test_failed_request_records_timing_and_only_safe_error(model, monkeypatch, status_code):
    clock = iter([10.0, 10.25])
    monkeypatch.setattr("chem_agent.model.perf_counter", lambda: next(clock))

    class ProviderError(Exception):
        def __init__(self):
            super().__init__("raw provider payload offline-dummy-key")
            self.status_code = status_code

    def provider_failure(_model, *_args, **_kwargs):
        model.trace.data["model_requests"].append({"status": "pending"})
        raise ProviderError()

    monkeypatch.setattr(OpenAIModel, "generate", provider_failure)
    with pytest.raises(ModelUnavailable):
        model.generate([])
    entry = model.trace.data["model_requests"][-1]
    assert entry["status"] == "failed"
    assert entry["latency_ms"] == 250
    assert entry["finished_at"]
    assert "raw provider payload" not in model.trace.path.read_text()
    assert "offline-dummy-key" not in model.trace.path.read_text()


def test_finished_task_cannot_make_another_provider_request(model, monkeypatch):
    model.trace.finish("needs_input", "请补参。")

    def forbidden_provider(*_args, **_kwargs):
        pytest.fail("A finished task must not make another provider request.")

    monkeypatch.setattr(OpenAIModel, "generate", forbidden_provider)
    with pytest.raises(ModelUnavailable, match="已经结束"):
        model.generate([])
    assert model.request_count == 0
    assert not model.trace.data["model_requests"]
    assert model.trace.data["status"] == "needs_input"


def test_failure_before_new_request_does_not_corrupt_previous_success(model, monkeypatch):
    previous = {"status": "succeeded", "latency_ms": 25}
    model.trace.data["model_requests"].append(previous.copy())

    def prepare_failure(_model, *_args, **_kwargs):
        raise ValueError("invalid completion arguments")

    monkeypatch.setattr(OpenAIModel, "generate", prepare_failure)
    with pytest.raises(ModelUnavailable):
        model.generate([])
    assert model.trace.data["model_requests"] == [previous]

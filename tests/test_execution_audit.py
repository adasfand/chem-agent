"""Observable model actions remain separate from private provider messages."""

from fastapi.testclient import TestClient
from smolagents import OpenAIModel
from smolagents.models import ChatMessage, ChatMessageToolCall, ChatMessageToolCallFunction

from chem_agent.config import Settings
from chem_agent.model import TracedModel
from chem_agent.trace import RunTrace
from chem_agent.ui import _Runtime


def test_public_model_events_expose_only_observable_fields(tmp_path):
    runtime = _Runtime(Settings(root=tmp_path, api_key="secret-test"))
    result = {
        "model_requests": [
            {
                "requested_at": "2026-10-12T00:00:00Z",
                "status": "succeeded",
                "latency_ms": 100,
                "selected_tools": ["convert_units"],
                "tool_names": ["search_knowledge", "convert_units"],
                "messages": [{"content": "private provider prompt secret-test"}],
                "reasoning_content": "private reasoning",
                "usage": {"input_tokens": 12, "output_tokens": 8, "private": "private"},
            }
        ],
    }
    public = runtime.clean_result(result)
    assert "model_requests" not in public
    assert public["model_events"] == [
        {
            "requested_at": "2026-10-12T00:00:00Z",
            "status": "succeeded",
            "latency_ms": 100,
            "selected_tools": ["convert_units"],
            "usage": {"input_tokens": 12, "output_tokens": 8},
        }
    ]
    assert "private" not in str(public)
    assert "messages" in result["model_requests"][0]
    assert "model_events" not in runtime.clean_result({"status": "completed"})


def test_selected_tools_are_response_actions_not_available_candidates(tmp_path, monkeypatch):
    trace = RunTrace(tmp_path, "test", {}, "test")
    model = TracedModel(Settings(root=tmp_path, api_key="offline-dummy-key"), trace)

    def response(_model, *_args, **_kwargs):
        trace.data["model_requests"].append({"tool_names": ["convert_units", "calc_heat_duty"]})
        return ChatMessage(
            role="assistant",
            tool_calls=[
                ChatMessageToolCall(
                    id="test",
                    type="function",
                    function=ChatMessageToolCallFunction(name="convert_units", arguments={}),
                )
            ],
        )

    monkeypatch.setattr(OpenAIModel, "generate", response)
    try:
        model.generate([])
        assert trace.data["model_requests"][0]["selected_tools"] == ["convert_units"]
    finally:
        model.client.close()


def test_old_trace_stays_unbatched_and_new_batch_metadata_is_public_without_messages(tmp_path):
    runtime = _Runtime(Settings(root=tmp_path, api_key="secret-test"))
    old = {"status": "completed", "calls": [], "plan": []}
    assert "tool_batches" not in runtime.clean_result(old)
    batch = {
        "batch_id": "batch_1",
        "agent_step": 1,
        "model_request_index": 1,
        "tool_names": ["set_plan", "convert_units"],
        "call_ids": ["call_1"],
        "status": "succeeded",
        "execution_mode": "ordered",
        "latency_ms": 2,
    }
    public = runtime.clean_result({**old, "tool_batches": [batch]})
    assert public["tool_batches"] == [batch]
    assert "messages" not in str(public) and "reasoning_content" not in str(public)


def test_model_request_allows_native_multiple_tool_selection(tmp_path):
    trace = RunTrace(tmp_path, "test", {}, "test")
    model = TracedModel(Settings(root=tmp_path, api_key="offline-dummy-key"), trace)
    try:
        request = model._prepare_completion_kwargs(messages=[])
        assert request.get("parallel_tool_calls") is not False
        assert request.get("extra_body", {}).get("parallel_tool_calls") is not False
    finally:
        model.client.close()


def test_tool_registry_routes_validate_body_and_whitelist(tmp_path):
    from chem_agent.ui import create_app

    (tmp_path / "examples").mkdir()
    (tmp_path / "examples" / "tasks.json").write_text("[]")
    app = create_app(Settings(root=tmp_path))
    base = "http://127.0.0.1:7860"
    with TestClient(app, base_url=base, headers={"Origin": base}) as client:
        assert (
            client.post(
                "/api/tool-registry/arbitrary_command/invoke", json={"arguments": {}}
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/api/tool-registry/inspect_unit_compatibility/invoke", json={"command": "anything"}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/tool-registry/inspect_unit_compatibility/invoke", content="invalid"
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/tool-registry/inspect_unit_compatibility/invoke",
                headers={"Origin": "http://evil.test"},
                json={"arguments": {}},
            ).status_code
            == 403
        )

"""Configurable model adapter with redacted request/response evidence."""
from smolagents import OpenAIModel


class TracedModel(OpenAIModel):
    def __init__(self, settings, trace):
        self.trace = trace
        super().__init__(model_id=settings.model_id, api_base=settings.api_base,
                         api_key=settings.api_key,
                         client_kwargs={"timeout": settings.timeout, "max_retries": 0},
                         retry=False)

    def generate(self, messages, **kwargs):
        self.trace.event("model_request", messages=messages,
                         tool_names=[t.name for t in kwargs.get("tools_to_call_from", []) or []])
        try:
            result = super().generate(messages, **kwargs)
            self.trace.event("model_response", content=result.content, tool_calls=result.tool_calls)
            return result
        except Exception as exc:
            self.trace.event("model_error", error=str(exc))
            raise

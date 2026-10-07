"""DeepSeek adapter with bounded requests and sanitized evidence logging."""

from __future__ import annotations

from copy import deepcopy
from time import perf_counter

from smolagents import OpenAIModel

from chem_agent.config import Settings
from chem_agent.trace import RunTrace, utc_now


class ModelUnavailable(RuntimeError):
    pass


class RunCancelled(RuntimeError):
    pass


class TracedModel(OpenAIModel):
    def __init__(self, settings: Settings, trace: RunTrace):
        if not settings.api_key:
            raise ModelUnavailable("尚未配置 DeepSeek 密钥。请填写本机 .env 后重试。")
        self.trace = trace
        self.request_count = 0
        self.request_limit = settings.max_steps + 1
        self.last_error = None
        self.cancel_event = None
        super().__init__(
            model_id=settings.model,
            api_base=settings.base_url,
            api_key=settings.api_key,
            client_kwargs={"timeout": settings.request_timeout, "max_retries": 0},
            retry=False,
            temperature=0,
            max_tokens=1800,
            extra_body={"thinking": {"type": "disabled"}},
        )

    def _prepare_completion_kwargs(self, *args, **kwargs):
        request = super()._prepare_completion_kwargs(*args, **kwargs)
        # Store tool observations actually passed to the model, without assistant reasoning.
        messages = deepcopy(request["messages"])
        for message in messages:
            message.pop("reasoning_content", None)
            if message.get("role") == "assistant":
                message["content"] = "[assistant commentary omitted]"
        self.trace.data["model_requests"].append(
            {
                "requested_at": utc_now(),
                "messages": messages,
                "tool_names": [t["function"]["name"] for t in request.get("tools", [])],
                "status": "pending",
            }
        )
        self.trace.save()
        return request

    def generate(self, *args, **kwargs):
        if self.trace.data["status"] != "running":
            raise ModelUnavailable("任务已经结束，不能继续请求模型。")
        if self.cancel_event and self.cancel_event.is_set():
            raise RunCancelled("任务已取消。")
        if self.last_error:
            raise ModelUnavailable(self.last_error)
        self.request_count += 1
        if self.request_count > self.request_limit:
            raise ModelUnavailable("已达到本次任务的模型请求上限。")
        started = perf_counter()
        request_index = len(self.trace.data["model_requests"])
        try:
            response = super().generate(*args, **kwargs)
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status in (401, 403):
                message = "DeepSeek 认证失败，请检查本机密钥与访问权限。"
            elif status == 402:
                message = "DeepSeek 账户余额不足。"
            elif status == 429:
                message = "DeepSeek 请求受限，请稍后重试。"
            else:
                message = "模型请求失败或超时，请检查网络、服务地址和模型名称后重试。"
            self.last_error = message
            if len(self.trace.data["model_requests"]) > request_index:
                self.trace.data["model_requests"][-1].update(
                    status="failed",
                    error=message,
                    finished_at=utc_now(),
                    latency_ms=round((perf_counter() - started) * 1000, 3),
                )
                self.trace.save()
            raise ModelUnavailable(message) from None
        entry = self.trace.data["model_requests"][-1]
        entry.update(
            status="succeeded",
            finished_at=utc_now(),
            latency_ms=round((perf_counter() - started) * 1000, 3),
        )
        usage = response.token_usage
        entry["usage"] = (
            {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
            if usage
            else {}
        )
        self.trace.save()
        if self.cancel_event and self.cancel_event.is_set():
            # The HTTP request cannot be interrupted here, but its proposed action
            # must never reach a tool after the user has cancelled the task.
            raise RunCancelled("任务已取消。")
        return response

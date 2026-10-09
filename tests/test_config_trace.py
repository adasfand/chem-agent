import json

import pytest

from chem_agent.config import Settings
from chem_agent.trace import RunTrace


def test_key_file_read_without_public_exposure(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY_FILE", raising=False)
    (tmp_path / "key.txt").write_text("sk-dummy-secret-not-a-real-key\n")
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY_FILE=key.txt\n")
    settings = Settings.load(tmp_path)
    assert settings.api_key == "sk-dummy-secret-not-a-real-key"
    assert settings.api_key not in repr(settings)
    assert settings.api_key not in json.dumps(settings.public())


def test_trace_redacts_nested_credentials(tmp_path):
    secret = "private-dummy-key"
    trace = RunTrace(tmp_path, f"用户输入{secret}", {}, "v1", (secret,))
    trace.data["calls"].append({"arguments": {"api_key": "other", "text": secret}})
    trace.finish("failed", "sk-abcdefghijklmnop")
    text = trace.path.read_text()
    assert secret not in text
    assert "sk-abcdefghijklmnop" not in text
    assert json.loads(text)["calls"][0]["arguments"]["api_key"] == "[redacted]"


@pytest.mark.parametrize(
    "url",
    ["http://example.com", "https://user:password@example.com", "https://example.com?key=secret"],
)
def test_insecure_or_credential_bearing_endpoint_rejected(tmp_path, monkeypatch, url):
    monkeypatch.setenv("DEEPSEEK_BASE_URL", url)
    with pytest.raises(ValueError):
        Settings.load(tmp_path)


@pytest.mark.parametrize(
    "url",
    [
        "https://",
        "https:///api",
        "https://:443",
        "https://example.org:invalid",
        "https://example.org:",
        "https://example.org:0",
        "https://example.org:65536",
        "https://[::1",
        "https://invalid host",
    ],
)
def test_malformed_model_endpoint_is_rejected_before_task(tmp_path, monkeypatch, url):
    monkeypatch.delenv("DEEPSEEK_API_KEY_FILE", raising=False)
    monkeypatch.setenv("DEEPSEEK_BASE_URL", url)
    with pytest.raises(ValueError, match="有效的主机和端口"):
        Settings.load(tmp_path)


@pytest.mark.parametrize(
    "url",
    [
        "https://api.deepseek.com",
        "https://example.org:443/v1",
        "http://localhost:8000/v1",
        "http://127.0.0.1:8000",
        "http://[::1]:8000/v1",
    ],
)
def test_valid_model_endpoint_preserves_supported_schemes(tmp_path, monkeypatch, url):
    monkeypatch.delenv("DEEPSEEK_API_KEY_FILE", raising=False)
    monkeypatch.setenv("DEEPSEEK_BASE_URL", url)
    assert Settings.load(tmp_path).base_url == url

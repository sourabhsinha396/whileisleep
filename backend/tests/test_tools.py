import httpx
import pytest

from apps.agent import http_tools
from apps.agent.models import Tool

from .factories import ToolFactory, VisitorFactory

pytestmark = pytest.mark.django_db


class Recorder:
    """Stands in for httpx.request."""

    def __init__(self, status=200, json=None, text=None, error=None):
        self.calls = []
        self.status, self.json, self.text, self.error = status, json, text, error

    def __call__(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if self.error:
            raise self.error
        request = httpx.Request(method, url)
        if self.json is not None:
            return httpx.Response(self.status, json=self.json, request=request)
        return httpx.Response(self.status, text=self.text or "", request=request)


@pytest.fixture
def http(monkeypatch):
    def install(**kwargs):
        recorder = Recorder(**kwargs)
        monkeypatch.setattr(http_tools.httpx, "request", recorder)
        return recorder

    return install


def test_get_fills_url_placeholders_and_query(http):
    tool = ToolFactory(url="https://api.example.com/exams/{code}", headers={"Authorization": "Bearer s3cret"})
    recorder = http(json={"code": "AZ-104", "available": True})
    result, is_error = http_tools.run(tool, {"code": "AZ 104", "lang": "en"}, VisitorFactory())
    call = recorder.calls[0]
    assert call["url"] == "https://api.example.com/exams/AZ%20104"
    assert call["params"] == {"lang": "en"}
    assert call["headers"] == {"Authorization": "Bearer s3cret"}
    assert result == '{"code":"AZ-104","available":true}'
    assert not is_error


def test_post_sends_json_body(http):
    tool = ToolFactory(method=Tool.Method.POST, url="https://api.example.com/search")
    recorder = http(json=[])
    http_tools.run(tool, {"q": "aws"}, VisitorFactory())
    assert recorder.calls[0]["json"] == {"q": "aws"}


def test_visitor_placeholders_come_from_the_visitor_not_the_model(http):
    tool = ToolFactory(url="https://api.example.com/orders?email={visitor.email}")
    recorder = http(json=[])
    http_tools.run(tool, {"visitor.email": "victim@example.com"}, VisitorFactory(email="me@example.com"))
    assert recorder.calls[0]["url"] == "https://api.example.com/orders?email=me%40example.com"


def test_http_error_is_reported_to_the_model(http):
    http(status=500, text="boom")
    result, is_error = http_tools.run(ToolFactory(), {}, VisitorFactory())
    assert is_error and result.startswith("HTTP 500")


def test_network_error_is_reported(http):
    http(error=httpx.ConnectError("refused"))
    result, is_error = http_tools.run(ToolFactory(), {}, VisitorFactory())
    assert is_error and "ConnectError" in result


def test_long_results_are_truncated(http):
    http(text="x" * 20000)
    result, _ = http_tools.run(ToolFactory(), {}, VisitorFactory())
    assert len(result) < http_tools.MAX_RESULT_CHARS + 50


# --- Tools API ---


def tool_payload(**overrides):
    return {
        "name": "search_products",
        "description": "Search the product catalog by keyword.",
        "method": "GET",
        "url": "https://shop.example.com/api/products",
        "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
        "headers": {"X-Api-Key": "sk_live_hidden"},
    } | overrides


def test_create_tool_hides_header_values(api, workspace):
    created = api.post(f"/workspaces/{workspace.id}/tools", tool_payload())
    assert created.status_code == 200
    assert created.json()["header_names"] == ["X-Api-Key"]
    assert "sk_live_hidden" not in str(api.get(f"/workspaces/{workspace.id}/tools").json())


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "Bad Name"},
        {"name": "search_knowledge_base"},
        {"method": "DELETE"},
        {"url": "ftp://x.example.com/thing"},
        {"input_schema": {"type": "string"}},
    ],
)
def test_invalid_tools_are_rejected(api, workspace, overrides):
    assert api.post(f"/workspaces/{workspace.id}/tools", tool_payload(**overrides)).status_code == 400


def test_update_keeps_headers_when_left_empty(api, workspace):
    tool = ToolFactory(workspace=workspace, headers={"X-Api-Key": "k"})
    api.put(f"/workspaces/{workspace.id}/tools/{tool.id}", tool_payload(headers={}))
    tool.refresh_from_db()
    assert tool.headers == {"X-Api-Key": "k"}


def test_test_endpoint_calls_the_tool(api, workspace, http):
    tool = ToolFactory(workspace=workspace)
    http(json={"ok": 1})
    tested = api.post(f"/workspaces/{workspace.id}/tools/{tool.id}/test", {"inputs": {"q": "x"}})
    assert tested.json() == {"result": '{"ok":1}', "is_error": False}

"""The MCP client, against scripted servers of both generations. No network."""

import json

import httpx
import pytest

from apps.agent import mcp
from whileisleep import outbound

URL = "https://mcp.example.com/mcp"
TOOL = {
    "name": "get_order",
    "description": "Look up an order by number.",
    "inputSchema": {"type": "object", "properties": {"number": {"type": "string"}}, "required": ["number"]},
    "annotations": {"readOnlyHint": True},
}


def rpc(result=None, error=None, id=1, status=200, headers=None, sse=False):
    """An HTTP response carrying a JSON-RPC response."""
    message = {"jsonrpc": "2.0", "id": id} | ({"error": error} if error else {"result": result or {}})
    if sse:
        body = 'event: message\ndata: {"jsonrpc":"2.0","method":"notifications/progress","params":{}}\n\n'
        body += f"event: message\ndata: {json.dumps(message)}\n\n"
        return httpx.Response(status, text=body, headers={"Content-Type": "text/event-stream", **(headers or {})})
    return httpx.Response(status, json=message, headers=headers or {})


class Server:
    """Stands in for outbound.request. `answer(body, headers)` returns the response."""

    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def __call__(self, method, url, *, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "body": json, "headers": headers})
        return self.answer(json, headers)

    @property
    def methods(self):
        return [call["body"]["method"] for call in self.calls]


@pytest.fixture
def serve(monkeypatch):
    def install(answer):
        server = Server(answer)
        monkeypatch.setattr(outbound, "request", server)
        return server

    return install


def modern_server(body, headers):
    """Speaks 2026-07-28: stateless, everything in _meta."""
    meta = body["params"].get("_meta", {})
    if meta.get("io.modelcontextprotocol/protocolVersion") != "2026-07-28":
        return rpc(error={"code": -32602, "message": "missing protocol version"}, id=body["id"], status=400)
    if body["method"] == "tools/list":
        return rpc({"resultType": "complete", "tools": [TOOL]}, id=body["id"])
    if body["method"] == "tools/call":
        text = f"Order {body['params']['arguments']['number']} shipped."
        return rpc({"resultType": "complete", "content": [{"type": "text", "text": text}]}, id=body["id"])
    return rpc(error={"code": -32601, "message": "Method not found"}, id=body["id"])


def legacy_server(body, headers):
    """Speaks 2025-06-18: needs the initialize handshake and the session id it hands out."""
    if body["method"] == "initialize":
        return rpc(
            {"protocolVersion": "2025-06-18", "capabilities": {}}, id=body["id"], headers={"Mcp-Session-Id": "s1"}
        )
    if body["method"] == "notifications/initialized":
        return httpx.Response(202)
    if headers.get("Mcp-Session-Id") != "s1":
        return rpc(error={"code": -32000, "message": "Bad Request: No valid session ID provided"}, status=400)
    if body["method"] == "tools/list":
        return rpc({"tools": [TOOL]}, id=body["id"])
    return rpc({"content": [{"type": "text", "text": "Order shipped."}]}, id=body["id"])


# --- Modern servers ---


def test_lists_tools_from_a_modern_server_in_one_request(serve):
    server = serve(modern_server)
    client = mcp.Client(URL, {"Authorization": "Bearer t0ken"})

    tools = client.list_tools()

    assert tools == [mcp.RemoteTool("get_order", "Look up an order by number.", TOOL["inputSchema"], read_only=True)]
    assert server.methods == ["tools/list"]
    assert client.era == mcp.MODERN
    call = server.calls[0]
    assert call["url"] == URL
    assert call["headers"]["Authorization"] == "Bearer t0ken"
    assert call["headers"]["Accept"] == "application/json, text/event-stream"
    assert call["headers"]["MCP-Protocol-Version"] == "2026-07-28"
    assert call["headers"]["Mcp-Method"] == "tools/list"
    meta = call["body"]["params"]["_meta"]
    assert meta["io.modelcontextprotocol/protocolVersion"] == "2026-07-28"
    assert meta["io.modelcontextprotocol/clientCapabilities"] == {}
    assert meta["io.modelcontextprotocol/clientInfo"]["name"] == "whileisleep"


def test_calls_a_tool_on_a_modern_server(serve):
    server = serve(modern_server)
    result, is_error = mcp.Client(URL).call_tool("get_order", {"number": "A-100"})
    assert (result, is_error) == ("Order A-100 shipped.", False)
    assert server.calls[0]["headers"]["Mcp-Name"] == "get_order"
    assert server.calls[0]["body"]["params"]["arguments"] == {"number": "A-100"}


def test_reads_a_response_sent_as_an_event_stream(serve):
    serve(lambda body, headers: rpc({"tools": [TOOL]}, id=body["id"], sse=True))
    assert [tool.name for tool in mcp.Client(URL).list_tools()] == ["get_order"]


# --- Legacy servers ---


def test_falls_back_to_the_handshake_for_a_legacy_server(serve):
    server = serve(legacy_server)
    client = mcp.Client(URL)

    assert [tool.name for tool in client.list_tools()] == ["get_order"]

    # One modern attempt, then initialize, the notification, and the real request.
    assert server.methods == ["tools/list", "initialize", "notifications/initialized", "tools/list"]
    assert client.era == mcp.LEGACY
    last = server.calls[-1]
    assert last["headers"]["Mcp-Session-Id"] == "s1" and last["headers"]["MCP-Protocol-Version"] == "2025-06-18"
    assert "_meta" not in last["body"]["params"]
    assert "id" not in server.calls[2]["body"]  # a notification has no id


def test_a_known_legacy_server_skips_the_probe(serve):
    server = serve(legacy_server)
    mcp.Client(URL, era=mcp.LEGACY).call_tool("get_order", {"number": "A-100"})
    assert server.methods == ["initialize", "notifications/initialized", "tools/call"]


def test_one_client_shakes_hands_once(serve):
    server = serve(legacy_server)
    client = mcp.Client(URL, era=mcp.LEGACY)
    client.list_tools()
    client.call_tool("get_order", {"number": "A-100"})
    assert server.methods.count("initialize") == 1


# --- Results ---


def test_pages_of_tools_are_followed(serve):
    def paged(body, headers):
        if body["params"].get("cursor") == "page2":
            return rpc({"tools": [TOOL | {"name": "second"}]}, id=body["id"])
        return rpc({"tools": [TOOL], "nextCursor": "page2"}, id=body["id"])

    serve(paged)
    assert [tool.name for tool in mcp.Client(URL).list_tools()] == ["get_order", "second"]


def test_a_server_that_pages_forever_is_cut_off(serve):
    server = serve(lambda body, headers: rpc({"tools": [TOOL], "nextCursor": "again"}, id=body["id"]))
    assert len(mcp.Client(URL).list_tools()) == mcp.MAX_PAGES
    assert len(server.calls) == mcp.MAX_PAGES


@pytest.mark.parametrize(
    "raw",
    [None, "get_order", {}, {"name": ""}, {"name": 7}, {"description": "nameless"}],
)
def test_malformed_tools_are_dropped(raw):
    assert mcp.parse_tool(raw) is None


def test_a_tool_with_a_bad_schema_gets_an_empty_one():
    tool = mcp.parse_tool({"name": "ping", "inputSchema": {"type": "string"}})
    assert tool.input_schema == {"type": "object", "properties": {}} and tool.read_only is False


@pytest.mark.parametrize(
    ("result", "text"),
    [
        ({"content": [{"type": "text", "text": "one"}, {"type": "text", "text": "two"}]}, "one\ntwo"),
        ({"content": [{"type": "image", "data": "..."}]}, "[image omitted]"),
        ({"content": [{"type": "resource_link", "uri": "https://x.example.com/a"}]}, "https://x.example.com/a"),
        ({"content": [], "structuredContent": {"status": "shipped"}}, '{"status":"shipped"}'),
        ({"content": [{"type": "text", "text": "summary"}], "structuredContent": {"a": 1}}, "summary"),
        ({}, "(the tool returned nothing)"),
        ({"content": ["junk", None]}, "(the tool returned nothing)"),
    ],
)
def test_tool_results_become_text(result, text):
    assert mcp.result_text(result) == text


def test_a_tool_error_is_passed_on_as_an_error(serve):
    serve(
        lambda body, headers: rpc(
            {"content": [{"type": "text", "text": "No such order."}], "isError": True}, id=body["id"]
        )
    )
    assert mcp.Client(URL).call_tool("get_order", {"number": "?"}) == ("No such order.", True)


# --- Failures ---


def test_rejected_credentials_are_reported_plainly(serve):
    serve(lambda body, headers: httpx.Response(401, text="nope"))
    with pytest.raises(mcp.McpError, match="credentials"):
        mcp.Client(URL).list_tools()


def test_a_protocol_error_carries_the_servers_message(serve):
    serve(lambda body, headers: rpc(error={"code": -32601, "message": "Method not found"}, id=body["id"]))
    with pytest.raises(mcp.McpError, match="Method not found"):
        mcp.Client(URL).list_tools()


def test_a_modern_only_error_is_not_retried_as_legacy(serve):
    server = serve(
        lambda body, headers: rpc(error={"code": -32022, "message": "Unsupported protocol version"}, status=400)
    )
    with pytest.raises(mcp.McpError, match="Unsupported protocol version"):
        mcp.Client(URL).list_tools()
    assert server.methods == ["tools/list"]


def test_when_neither_way_works_the_first_answer_is_reported(serve):
    serve(lambda body, headers: httpx.Response(400, text="go away"))
    with pytest.raises(mcp.McpError, match="HTTP 400"):
        mcp.Client(URL).list_tools()


def test_a_page_that_is_not_mcp_is_an_error(serve):
    serve(lambda body, headers: httpx.Response(200, text="<html>hello</html>"))
    with pytest.raises(mcp.McpError, match="without a usable response"):
        mcp.Client(URL).list_tools()


def test_a_server_asking_for_input_is_refused(serve):
    serve(lambda body, headers: rpc({"resultType": "input_required", "inputRequests": []}, id=body["id"]))
    with pytest.raises(mcp.McpError, match="more input"):
        mcp.Client(URL).call_tool("get_order", {})


def test_network_failures_and_private_addresses_are_errors(monkeypatch):
    def unreachable(*args, **kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(outbound, "request", unreachable)
    with pytest.raises(mcp.McpError, match="ConnectError"):
        mcp.Client(URL).list_tools()

    monkeypatch.undo()
    monkeypatch.setattr(outbound, "resolve", lambda host, port: ["10.0.0.5"])
    with pytest.raises(mcp.McpError, match="private network"):
        mcp.Client("http://internal.example.com/mcp").list_tools()


def test_event_streams_with_junk_are_tolerated():
    stream = 'data: not json\n\n: a comment\n\ndata: {"jsonrpc":"2.0","id":3,\ndata: "result":{"ok":true}}\n\n'
    assert mcp.sse_messages(stream) == [{"jsonrpc": "2.0", "id": 3, "result": {"ok": True}}]

"""A small Model Context Protocol client: list a server's tools, call one.

MCP is how other products expose tools to AI agents, so a workspace can plug in a server
(its own, or Stripe's, Shopify's...) instead of describing each endpoint by hand. This is
the wire protocol only; apps.agent.mcp_tools decides which tools the AI may use.

Two generations of servers exist and one client has to talk to both:

- *Modern* (spec 2026-07-28): stateless. Every request carries the protocol version and
  client info in `params._meta`; there is no handshake and no session.
- *Legacy* (2025 specs): `initialize`, then `notifications/initialized`, then requests that
  carry the session id the server handed out.

Following the spec's advice, we try a modern request first and fall back to the legacy
handshake when the server answers 400 without a modern error. The caller remembers which
kind a server is (`era`) so later calls skip the probe.

Transport is Streamable HTTP: a JSON-RPC request per POST, answered with JSON or with a
short server-sent-event stream that ends in the response. All requests go through
whileisleep.outbound, so a server URL can't point into our own network.
"""

import json
from dataclasses import dataclass, field

import httpx

from whileisleep import outbound

MODERN = "modern"
LEGACY = "legacy"
MODERN_VERSION = "2026-07-28"
LEGACY_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "whileisleep", "version": "0.1.0"}
TIMEOUT_SECONDS = 20
MAX_TOOLS = 200
MAX_PAGES = 10
# JSON-RPC error codes only a modern server sends: the request reached one, so there is no
# point retrying it as legacy.
MODERN_ERRORS = {-32020, -32022}


class McpError(Exception):
    """The server couldn't be used. The message is safe to show the workspace's team."""


@dataclass(frozen=True)
class RemoteTool:
    name: str
    description: str
    input_schema: dict
    # The server's own claim that the tool changes nothing. A hint, not a guarantee.
    read_only: bool = False


@dataclass
class Client:
    url: str
    # Sent with every request, e.g. {"Authorization": "Bearer ..."}.
    headers: dict = field(default_factory=dict)
    # MODERN or LEGACY once known; None probes.
    era: str | None = None
    _session: dict | None = None
    _next_id: int = 0

    # --- What callers use ---

    def list_tools(self) -> list[RemoteTool]:
        tools: list[RemoteTool] = []
        cursor = None
        for _ in range(MAX_PAGES):
            result = self.request("tools/list", {"cursor": cursor} if cursor else {})
            for raw in result.get("tools") or []:
                tool = parse_tool(raw)
                if tool is not None:
                    tools.append(tool)
            cursor = result.get("nextCursor")
            if not cursor or len(tools) >= MAX_TOOLS:
                break
        return tools[:MAX_TOOLS]

    def call_tool(self, name: str, arguments: dict) -> tuple[str, bool]:
        """Returns (text for the model, is_error)."""
        result = self.request("tools/call", {"name": name, "arguments": arguments or {}}, tool_name=name)
        return result_text(result), bool(result.get("isError"))

    # --- One JSON-RPC request, in whichever dialect the server speaks ---

    def request(self, method: str, params: dict, tool_name: str = "") -> dict:
        if self.era == LEGACY:
            return self.legacy(method, params)
        try:
            result = self.modern(method, params, tool_name)
        except _NotModern as first:
            if self.era == MODERN:
                raise McpError(str(first)) from first
            try:
                result = self.legacy(method, params)
            except McpError:
                # Neither dialect worked; the first answer is the more telling one.
                raise McpError(str(first)) from first
            self.era = LEGACY
            return result
        self.era = MODERN
        return result

    def modern(self, method: str, params: dict, tool_name: str = "") -> dict:
        meta = {
            "io.modelcontextprotocol/protocolVersion": MODERN_VERSION,
            "io.modelcontextprotocol/clientInfo": CLIENT_INFO,
            # None declared, so the server may not ask us for input mid-call.
            "io.modelcontextprotocol/clientCapabilities": {},
        }
        headers = {"MCP-Protocol-Version": MODERN_VERSION, "Mcp-Method": method}
        if tool_name:
            headers["Mcp-Name"] = tool_name
        response = self.post({"method": method, "params": {**params, "_meta": meta}}, headers)
        if response.status_code == 400:
            error = rpc_error(response)
            if error is None or error.get("code") not in MODERN_ERRORS:
                raise _NotModern(describe(response, error))
        result = self.result_of(response)
        if result.get("resultType", "complete") != "complete":
            raise McpError("The server asked for more input than this client can give.")
        return result

    def legacy(self, method: str, params: dict) -> dict:
        if self._session is None:
            self._session = self.handshake()
        return self.result_of(self.post({"method": method, "params": params}, self._session))

    def handshake(self) -> dict:
        """The 2025 `initialize` exchange. Returns the headers later requests must carry."""
        params = {"protocolVersion": LEGACY_VERSION, "capabilities": {}, "clientInfo": CLIENT_INFO}
        response = self.post({"method": "initialize", "params": params}, {})
        result = self.result_of(response)
        headers = {"MCP-Protocol-Version": str(result.get("protocolVersion") or LEGACY_VERSION)}
        session_id = response.headers.get("Mcp-Session-Id")
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        # A notification: no id, and no answer to wait for.
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"}, headers)
        return headers

    # --- HTTP ---

    def post(self, message: dict, headers: dict) -> httpx.Response:
        self._next_id += 1
        return self.send({"jsonrpc": "2.0", "id": self._next_id, **message}, headers)

    def send(self, body: dict, headers: dict) -> httpx.Response:
        try:
            return outbound.request(
                "POST",
                self.url,
                json=body,
                headers={
                    **{str(k): str(v) for k, v in self.headers.items()},
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                    **headers,
                },
                timeout=TIMEOUT_SECONDS,
            )
        except outbound.BlockedAddress as error:
            raise McpError(str(error)) from error
        except httpx.HTTPError as error:
            raise McpError(f"Could not reach the MCP server: {type(error).__name__}") from error

    def result_of(self, response: httpx.Response) -> dict:
        """The `result` of the JSON-RPC response in an HTTP response, or McpError."""
        if response.status_code in (401, 403):
            raise McpError("The MCP server refused the credentials (check the token).")
        message = rpc_message(response, self._next_id)
        if message is None:
            raise McpError(describe(response, None))
        if "error" in message:
            raise McpError(describe(response, message["error"]))
        result = message.get("result")
        if response.status_code >= 400 or not isinstance(result, dict):
            raise McpError(describe(response, None))
        return result


class _NotModern(Exception):
    """A modern request got a 400 that a modern server wouldn't send: try the legacy way."""


# --- Reading responses ---


def rpc_message(response: httpx.Response, request_id: int) -> dict | None:
    """The JSON-RPC response to our request, from a JSON body or an event stream."""
    if "text/event-stream" in response.headers.get("Content-Type", ""):
        candidates = sse_messages(response.text)
    else:
        try:
            candidates = [response.json()]
        except ValueError:
            return None
    replies = [m for m in candidates if isinstance(m, dict) and ("result" in m or "error" in m)]
    for message in replies:
        if message.get("id") == request_id:
            return message
    # Servers that answer errors without echoing the id still mean this request.
    return replies[-1] if replies else None


def sse_messages(text: str) -> list:
    """The JSON payloads of a server-sent-event stream. Progress notifications may come
    before the response; unparsable events are skipped."""
    messages, data = [], []

    def flush():
        if data:
            try:
                messages.append(json.loads("\n".join(data)))
            except ValueError:
                pass
            data.clear()

    for line in text.replace("\r\n", "\n").split("\n"):
        if not line.strip():
            flush()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
    flush()
    return messages


def rpc_error(response: httpx.Response) -> dict | None:
    message = rpc_message(response, -1)
    error = message.get("error") if message else None
    return error if isinstance(error, dict) else None


def describe(response: httpx.Response, error: dict | None) -> str:
    if error and error.get("message"):
        return f"The MCP server answered with an error: {str(error['message'])[:300]}"
    return f"The MCP server answered HTTP {response.status_code} without a usable response."


def parse_tool(raw) -> RemoteTool | None:
    """A tool from `tools/list`, or None when it is too malformed to offer."""
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not raw["name"].strip():
        return None
    schema = raw.get("inputSchema")
    if not isinstance(schema, dict) or schema.get("type", "object") != "object":
        schema = {"type": "object", "properties": {}}
    annotations = raw.get("annotations") if isinstance(raw.get("annotations"), dict) else {}
    return RemoteTool(
        name=raw["name"].strip(),
        description=str(raw.get("description") or raw.get("title") or "").strip(),
        input_schema=schema,
        read_only=annotations.get("readOnlyHint") is True,
    )


def result_text(result: dict) -> str:
    """A `tools/call` result as text for the model."""
    parts = []
    for item in result.get("content") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            parts.append(str(item.get("text", "")))
        elif item.get("type") == "resource_link":
            parts.append(str(item.get("uri", "")))
        else:
            # Images, audio and embedded files can't go into a text reply.
            parts.append(f"[{item.get('type', 'content')} omitted]")
    text = "\n".join(part for part in parts if part)
    if not text and result.get("structuredContent") is not None:
        text = json.dumps(result["structuredContent"], separators=(",", ":"), ensure_ascii=False)
    return text or "(the tool returned nothing)"

"""Synchronous Agent adapter for the official asynchronous MCP client."""

from __future__ import annotations

import json
import threading

import anyio
from anyio.from_thread import BlockingPortal, start_blocking_portal
from mcp import Client

from codepilot.schemas import FunctionSpec, ToolCall, ToolResult, ToolSpec
from codepilot.tools.registry import ToolRegistry


ALLOWED_REPOSITORY_TOOLS = frozenset(
    {"repo_search", "repo_read", "repo_diff", "test_status", "run_tests"}
)
READ_ONLY_TOOLS = frozenset(
    {"repo_search", "repo_read", "repo_diff", "test_status"}
)


class MCPClientError(RuntimeError):
    """Raised when the MCP connection cannot be initialized."""


class MCPToolRegistry:
    """Bridge MCP tools to Agent's registry interface; server owns execution policy."""

    def __init__(
        self,
        server: object,
        *,
        timeout_seconds: float = 30,
        execution_mode: str = "docker",
        host_tests_approved: bool = False,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._server = server
        self._timeout = timeout_seconds
        self.execution_mode = execution_mode
        self.host_tests_approved = host_tests_approved
        self._approved_call_ids: set[str] = set()
        self._portal_cm = None
        self._portal: BlockingPortal | None = None
        self._request_send = None
        self._reply_receive = None
        self._worker = None
        self._request_lock = threading.Lock()
        self._specs: tuple[ToolSpec, ...] = ()
        self._tool_names: set[str] = set()

    def __enter__(self) -> "MCPToolRegistry":
        self._portal_cm = start_blocking_portal(backend="asyncio")
        self._portal = self._portal_cm.__enter__()
        try:
            self._request_send, request_receive = anyio.create_memory_object_stream(10)
            reply_send, self._reply_receive = anyio.create_memory_object_stream(10)
            self._worker = self._portal.start_task_soon(
                self._client_worker, request_receive, reply_send
            )
            listed = self._request("list_tools")
            discovered = [
                tool for tool in listed.tools if tool.name in ALLOWED_REPOSITORY_TOOLS
            ]
            self._tool_names = {tool.name for tool in discovered}
            self._specs = tuple(
                ToolSpec(
                    function=FunctionSpec(
                        name=tool.name,
                        description=tool.description or tool.name,
                        parameters=tool.input_schema,
                        strict=False,
                    )
                )
                for tool in discovered
            )
            if not self._specs:
                raise MCPClientError("MCP server exposed no allowed repository tools")
            return self
        except Exception as exc:
            self.__exit__(None, None, None)
            if isinstance(exc, MCPClientError):
                raise
            raise MCPClientError(f"MCP connection failed: {type(exc).__name__}") from exc

    def __exit__(self, exc_type, exc, traceback) -> None:
        try:
            if self._request_send is not None:
                self._portal.call(self._request_send.aclose)
        finally:
            if self._portal_cm is not None:
                self._portal_cm.__exit__(exc_type, exc, traceback)
            self._portal = None
            self._portal_cm = None
            self._request_send = None
            self._reply_receive = None
            self._worker = None

    def read_tools(self) -> tuple[ToolSpec, ...]:
        self._require_open()
        return self._specs

    def requires_approval(self, call: ToolCall) -> bool:
        if call.id in self._approved_call_ids:
            return False
        return (
            call.name == "run_tests"
            and self.execution_mode == "host"
            and not self.host_tests_approved
        )

    def approve(self, call: ToolCall) -> None:
        self._approved_call_ids.add(call.id)

    def execute(self, call: ToolCall) -> ToolResult:
        self._require_open()
        if call.name not in self._tool_names:
            return ToolResult(
                tool_name=call.name,
                ok=False,
                stderr=f"unknown or disallowed MCP tool: {call.name}",
                error_type="policy",
            )
        if self.requires_approval(call):
            return ToolResult(
                tool_name=call.name,
                ok=False,
                stderr="host test execution requires approval",
                error_type="PermissionError",
            )
        try:
            result = self._request("call_tool", call.name, call.arguments)
        except TimeoutError:
            return ToolResult(
                tool_name=call.name,
                ok=False,
                stderr="MCP tool request timed out",
                error_type="timeout",
            )
        except Exception as exc:
            return ToolResult(
                tool_name=call.name,
                ok=False,
                stderr=f"MCP tool request failed: {type(exc).__name__}",
                error_type="mcp_connection",
            )

        content = "\n".join(
            item.text for item in result.content if getattr(item, "type", None) == "text"
        )
        payload = result.structured_content
        if result.is_error and content:
            try:
                payload = json.loads(content)
            except json.JSONDecodeError:
                payload = None
                start = content.find("{")
                if start >= 0:
                    try:
                        payload = json.loads(content[start:])
                    except json.JSONDecodeError:
                        payload = None
        if isinstance(payload, dict) and "ok" in payload:
            return ToolResult(
                tool_name=call.name,
                ok=bool(payload["ok"]),
                exit_code=payload.get("exit_code"),
                stdout=str(payload.get("stdout") or ""),
                stderr=str(payload.get("stderr") or ""),
                duration_ms=int(payload.get("duration_ms") or 0),
                error_type=payload.get("error_type"),
            )
        if not content and result.structured_content is not None:
            content = str(result.structured_content)
        return ToolResult(
            tool_name=call.name,
            ok=not result.is_error,
            stdout=content if not result.is_error else "",
            stderr=content if result.is_error else "",
            error_type="mcp_tool" if result.is_error else None,
        )

    def execute_many(self, calls: list[ToolCall]) -> list[ToolResult]:
        return [self.execute(call) for call in calls]

    def can_execute_many_in_parallel(self, calls: list[ToolCall]) -> bool:
        # MCP request/reply pairs share one session and remain ordered.
        return False

    def _request(self, method_name: str, *args):
        self._require_portal()
        with self._request_lock:
            return self._portal.call(self._exchange, method_name, args)

    async def _exchange(self, method_name: str, args: tuple):
        await self._request_send.send((method_name, args))
        outcome, result = await self._reply_receive.receive()
        if outcome == "timeout":
            raise TimeoutError
        if outcome == "error":
            raise RuntimeError(result)
        return result

    async def _client_worker(self, request_receive, reply_send) -> None:
        async with Client(self._server, read_timeout_seconds=self._timeout) as client:
            async with request_receive, reply_send:
                async for method_name, args in request_receive:
                    try:
                        with anyio.fail_after(self._timeout):
                            result = await getattr(client, method_name)(*args)
                    except TimeoutError:
                        await reply_send.send(("timeout", None))
                    except Exception as exc:
                        await reply_send.send(("error", type(exc).__name__))
                    else:
                        await reply_send.send(("ok", result))

    def _require_open(self) -> None:
        if self._portal is None or self._request_send is None:
            raise MCPClientError("MCPToolRegistry must be used inside a with block")

    def _require_portal(self) -> None:
        if self._portal is None:
            raise MCPClientError("MCP client is not connected")


class HybridMCPToolRegistry:
    """Use MCP for repository reads/tests and local ToolRegistry for patch/diff."""

    _remote_aliases = {
        "search_code": "repo_search",
        "read_file": "repo_read",
        "test_status": "test_status",
        "run_tests": "run_tests",
    }

    def __init__(self, local: ToolRegistry, remote: MCPToolRegistry) -> None:
        self.local = local
        self.remote = remote
        self._remote_tool_names = {
            spec.function.name for spec in remote.read_tools()
        }

    def read_tools(self) -> tuple[ToolSpec, ...]:
        local_specs = {
            spec.function.name: spec for spec in self.local.read_tools()
        }
        remote_specs = {
            spec.function.name: spec for spec in self.remote.read_tools()
        }
        selected = [local_specs["apply_patch"], local_specs["git_diff"]]
        for local_name, remote_name in self._remote_aliases.items():
            if remote_name not in remote_specs:
                continue
            remote_spec = remote_specs[remote_name]
            selected.append(
                remote_spec.model_copy(
                    update={
                        "function": remote_spec.function.model_copy(
                            update={"name": local_name}
                        )
                    }
                )
            )
        return tuple(selected)

    def requires_approval(self, call: ToolCall) -> bool:
        remote_name = self._remote_aliases.get(call.name)
        if remote_name:
            return self.remote.requires_approval(
                call.model_copy(update={"name": remote_name})
            )
        return self.local.requires_approval(call)

    def approve(self, call: ToolCall) -> None:
        remote_name = self._remote_aliases.get(call.name)
        if remote_name:
            self.remote.approve(call.model_copy(update={"name": remote_name}))
        else:
            self.local.approve(call)

    def execute(self, call: ToolCall) -> ToolResult:
        remote_name = self._remote_aliases.get(call.name)
        if remote_name:
            if remote_name not in self._remote_tool_names:
                return ToolResult(
                    tool_name=call.name,
                    ok=False,
                    stderr=f"MCP server did not expose required tool: {remote_name}",
                    error_type="policy",
                )
            result = self.remote.execute(call.model_copy(update={"name": remote_name}))
            return result.model_copy(update={"tool_name": call.name})
        return self.local.execute(call)

    def execute_many(self, calls: list[ToolCall]) -> list[ToolResult]:
        return [self.execute(call) for call in calls]

    def can_execute_many_in_parallel(self, calls: list[ToolCall]) -> bool:
        return len(calls) > 1 and all(
            call.name in {"search_code", "read_file", "test_status"}
            for call in calls
        )

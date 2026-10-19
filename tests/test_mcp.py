import asyncio
from pathlib import Path

from mcp import Client
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from codepilot.mcp_client import MCPToolRegistry
from codepilot.mcp_server import create_server
from codepilot.schemas import ToolCall


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    (repo / "sample.py").write_text("def calculate():\n    return 2\n", encoding="utf-8")
    (repo / ".env").write_text("SECRET=never-read\n", encoding="utf-8")
    return repo


def test_mcp_lists_only_allowlisted_tools_and_exposes_schema(tmp_path) -> None:
    server = create_server(make_repo(tmp_path), ["python", "-m", "pytest"])

    async def discover():
        async with Client(server) as client:
            result = await client.list_tools()
            return result.tools

    tools = asyncio.run(discover())
    by_name = {tool.name: tool for tool in tools}
    assert set(by_name) == {
        "repo_search", "repo_read", "repo_diff", "test_status", "run_tests"
    }
    assert "query" in by_name["repo_search"].input_schema["properties"]
    assert "reason" in by_name["repo_read"].input_schema["required"]
    assert by_name["repo_search"].annotations.read_only_hint is True


def test_mcp_client_calls_registry_tools_and_maps_result(tmp_path) -> None:
    server = create_server(make_repo(tmp_path), ["python", "-m", "pytest"])

    with MCPToolRegistry(server) as tools:
        specs = {item.function.name: item.function for item in tools.read_tools()}
        assert "repo_search" in specs
        result = tools.execute(
            ToolCall(
                id="read-1",
                name="repo_read",
                arguments={
                    "path": "sample.py",
                    "reason": "确认任务提及的函数实现。",
                    "start_line": 1,
                },
            )
        )

    assert result.ok
    assert "def calculate" in result.stdout


def test_mcp_rejects_traversal_sensitive_paths_and_unlisted_tools(tmp_path) -> None:
    server = create_server(make_repo(tmp_path), ["python", "-m", "pytest"])

    async def attack():
        async with Client(server) as client:
            traversal = await client.call_tool(
                "repo_read",
                {"path": "../outside.txt", "reason": "读取仓库外文件。"},
            )
            sensitive = await client.call_tool(
                "repo_read", {"path": ".env", "reason": "读取配置。"}
            )
            unauthorized = await client.call_tool(
                "apply_patch", {"path": "sample.py", "old_text": "2", "new_text": "3"}
            )
            return traversal, sensitive, unauthorized

    traversal, sensitive, unauthorized = asyncio.run(attack())
    assert traversal.is_error
    assert sensitive.is_error
    assert unauthorized.is_error
    assert "never-read" not in str(sensitive.content)
    assert (tmp_path / "repo" / "sample.py").read_text(encoding="utf-8").endswith("return 2\n")


def test_mcp_client_blocks_tool_outside_discovered_allowlist(tmp_path) -> None:
    server = MCPServer("malicious-mcp")

    @server.tool(name="repo_search", annotations=ToolAnnotations(readOnlyHint=True))
    def repo_search(query: str) -> str:
        return query

    @server.tool(name="delete_everything")
    def delete_everything() -> str:
        return "should not be discoverable"

    with MCPToolRegistry(server) as tools:
        result = tools.execute(
            ToolCall(id="evil", name="delete_everything", arguments={})
        )

    assert not result.ok
    assert result.error_type == "policy"


def test_mcp_client_maps_request_timeout(tmp_path) -> None:
    server = MCPServer("slow-mcp")

    @server.tool(name="repo_search", annotations=ToolAnnotations(readOnlyHint=True))
    async def repo_search(query: str) -> str:
        await asyncio.sleep(2)
        return query

    with MCPToolRegistry(server, timeout_seconds=1) as tools:
        result = tools.execute(
            ToolCall(id="slow", name="repo_search", arguments={"query": "x"})
        )

    assert not result.ok
    assert result.error_type == "timeout"


def test_mcp_host_test_requires_local_approval(tmp_path) -> None:
    server = create_server(
        make_repo(tmp_path),
        ["python", "-m", "pytest"],
        execution_mode="host",
        host_tests_approved=True,
    )
    with MCPToolRegistry(server, execution_mode="host") as tools:
        call = ToolCall(id="host-test", name="run_tests", arguments={})
        assert tools.requires_approval(call)
        denied = tools.execute(call)
        assert not denied.ok
        assert denied.error_type == "PermissionError"

    unapproved_server = create_server(
        make_repo(tmp_path / "unapproved"),
        ["python", "-m", "pytest"],
        execution_mode="host",
        host_tests_approved=False,
    )

    async def list_unapproved_tools():
        async with Client(unapproved_server) as client:
            return (await client.list_tools()).tools

    assert "run_tests" not in {
        tool.name for tool in asyncio.run(list_unapproved_tools())
    }


def test_mcp_preserves_test_status_and_failure_details(tmp_path) -> None:
    repo = make_repo(tmp_path)
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_failure.py").write_text(
        "def test_expected_failure():\n    assert 1 == 2\n", encoding="utf-8"
    )
    server = create_server(
        repo,
        ["python", "-m", "pytest", "tests", "-q"],
        execution_mode="host",
        host_tests_approved=True,
    )

    with MCPToolRegistry(
        server, execution_mode="host", host_tests_approved=True
    ) as tools:
        result = tools.execute(
            ToolCall(id="failed-test", name="run_tests", arguments={})
        )
        status = tools.execute(
            ToolCall(id="status-after-test", name="test_status", arguments={})
        )

    assert not result.ok
    assert result.exit_code == 1
    assert result.error_type == "test_failure"
    assert "assert 1 == 2" in result.stdout
    assert status.ok
    assert "失败" in status.stdout

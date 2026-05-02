import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.models import CredentialType
from app.services.llm_trace import LLMTraceContext


class ExecuteLlmWithToolsMcpTraceTests(unittest.IsolatedAsyncioTestCase):
    async def test_records_mcp_tool_call_trace(self) -> None:
        from app.services.llm_service import execute_llm_with_tools

        tool_call = SimpleNamespace(
            id="call_1",
            type="function",
            function=SimpleNamespace(name="search_docs", arguments='{"query": "traces"}'),
        )
        first_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[tool_call]))],
            usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3),
        )
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = first_response

        trace_context = LLMTraceContext(
            user_id=uuid.uuid4(),
            credential_id=uuid.uuid4(),
            workflow_id=uuid.uuid4(),
            node_id="agent1",
            node_label="Agent",
        )

        tools = [
            {
                "name": "search_docs",
                "description": "Search docs",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
                "_source": "mcp",
                "_mcp_server": "docs",
                "_connection_id": "docs-conn",
            }
        ]

        def tool_executor(
            _tool_def: dict,
            _name: str,
            _args: dict,
            _timeout_seconds: float,
        ) -> dict:
            return {"matches": ["trace docs"]}

        with (
            patch(
                "app.services.llm_service.LLMService._get_client",
                return_value=(fake_client, "OpenAI"),
            ),
            patch("app.services.context_compressor.get_context_limit", return_value=128000),
            patch(
                "app.services.context_compressor.maybe_compress_messages",
                AsyncMock(side_effect=lambda messages, **_kwargs: (messages, None)),
            ),
            patch("app.services.llm_service.record_llm_trace") as record_trace,
        ):
            result = await execute_llm_with_tools(
                credential_type=CredentialType.openai.value,
                api_key="test-key",
                base_url=None,
                model="gpt-test",
                system_instruction=None,
                user_message="Search docs",
                tools=tools,
                tool_executor=tool_executor,
                max_tool_iterations=1,
                trace_context=trace_context,
            )

        self.assertEqual(result["tool_calls"][0]["source"], "mcp")
        mcp_trace_calls = [
            call
            for call in record_trace.call_args_list
            if call.kwargs.get("request_type") == "mcp.call_tool"
        ]
        self.assertEqual(len(mcp_trace_calls), 1)
        trace_kwargs = mcp_trace_calls[0].kwargs
        self.assertEqual(trace_kwargs["context"], trace_context)
        self.assertEqual(trace_kwargs["provider"], "MCP")
        self.assertEqual(trace_kwargs["request"]["tool_name"], "search_docs")
        self.assertEqual(trace_kwargs["request"]["mcp_server"], "docs")
        self.assertEqual(trace_kwargs["request"]["connection_id"], "docs-conn")
        self.assertEqual(trace_kwargs["response"], {"result": {"matches": ["trace docs"]}})
        self.assertIsNone(trace_kwargs["error"])


if __name__ == "__main__":
    unittest.main()

"""上游 SSE 解析测试。"""

from __future__ import annotations

from app.infra.upstream import chunk_from_openai, parse_sse_data


def test_parse_sse_data_valid() -> None:
    assert parse_sse_data('data: {"a": 1}') == {"a": 1}


def test_parse_sse_data_ignores_noise() -> None:
    assert parse_sse_data("") is None
    assert parse_sse_data(": keep-alive") is None
    assert parse_sse_data("event: message") is None
    assert parse_sse_data("data: [DONE]") is None
    assert parse_sse_data("data: not-json") is None
    assert parse_sse_data("data: [1, 2]") is None


def test_chunk_from_openai_extracts_text_and_usage() -> None:
    chunk = chunk_from_openai(
        {"choices": [{"delta": {"content": "嗨"}}], "usage": {"prompt_tokens": 3}}
    )
    assert chunk.text == "嗨"
    assert chunk.usage == {"prompt_tokens": 3}


def test_chunk_from_openai_handles_empty() -> None:
    chunk = chunk_from_openai({"choices": []})
    assert chunk.text is None
    assert chunk.usage is None

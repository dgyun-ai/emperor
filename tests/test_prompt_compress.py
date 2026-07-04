"""Tests for prompt and compression."""

from __future__ import annotations

from context.compressor import compress_messages, estimate_tokens, should_compress
from prompt.builder import PromptBuilder
from prompt.context_files import parse_file_references


def test_prompt_builder_tiers():
    pb = PromptBuilder(base_instructions="Base")
    pb.set_memory("Mem")
    text = pb.build()
    assert "Base" in text
    assert "Mem" in text


def test_prompt_builder_zh_language():
    pb = PromptBuilder(language="zh")
    text = pb.build()
    assert "简体中文" in text


def test_compress_protects_last_n():
    msgs = [{"role": "user", "content": f"msg {i}"} for i in range(30)]
    compressed = compress_messages(msgs, protect_last_n=5)
    assert len(compressed) == 6  # 1 summary + 5 protected


def test_should_compress_threshold():
    msgs = [{"role": "user", "content": "x" * 200000}]
    assert should_compress(msgs, threshold=0.5, max_context_tokens=100_000)


def test_estimate_tokens():
    assert estimate_tokens([{"role": "user", "content": "abcd"}]) >= 1


def test_parse_file_reference(tmp_path):
    f = tmp_path / "ref.md"
    f.write_text("referenced content")
    expanded, refs = parse_file_references(f"see @{f.name}", cwd=tmp_path)
    assert "referenced content" in expanded

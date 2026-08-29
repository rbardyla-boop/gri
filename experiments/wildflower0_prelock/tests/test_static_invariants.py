from __future__ import annotations

import ast
from pathlib import Path

CORE = Path(__file__).parents[1] / "wildflower0"

FORBIDDEN_IMPORTS = {"transformers", "tokenizers", "sentencepiece", "openai", "anthropic"}
FORBIDDEN_FIELD_NAMES = {"prompt", "instruction", "instructions", "message_to_engine", "natural_language_instruction"}


def test_no_tokenizer_or_llm_dependency_in_core() -> None:
    for path in CORE.glob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in FORBIDDEN_IMPORTS, (path, alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in FORBIDDEN_IMPORTS, (path, node.module)


def test_no_forbidden_internal_packet_field_names() -> None:
    for path in CORE.glob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert node.value not in FORBIDDEN_FIELD_NAMES, (path, node.lineno, node.value)

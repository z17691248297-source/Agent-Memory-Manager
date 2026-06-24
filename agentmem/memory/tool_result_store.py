from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agentmem.memory.memory_object import estimate_tokens
from agentmem.tools.result import ToolResult


class ToolResultStore:
    """工具结果外置存储，负责原文、索引、chunk 和摘要规则。"""

    def __init__(
        self,
        root_dir: str | Path = "results/tool_store",
        chunk_chars: int = 4000,
    ) -> None:
        self.root_dir = Path(root_dir)
        self.raw_dir = self.root_dir / "raw"
        self.index_dir = self.root_dir / "index"
        self.chunk_dir = self.root_dir / "chunks"
        self.chunk_chars = chunk_chars
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.chunk_dir.mkdir(parents=True, exist_ok=True)

    def save(self, tool_result: ToolResult) -> ToolResult:
        raw_path = self.raw_dir / f"{tool_result.result_id}.txt"
        raw_path.write_text(tool_result.raw_result, encoding="utf-8")

        chunks = self._write_chunks(tool_result.result_id, tool_result.raw_result)
        tool_result.raw_path = str(raw_path)
        tool_result.chunks = chunks
        tool_result.metadata["tool_compression_ratio"] = tool_result.compression_ratio

        index_path = self.index_dir / f"{tool_result.result_id}.json"
        index_path.write_text(
            json.dumps(tool_result.to_dict(include_raw=False), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return tool_result

    def load(self, result_id: str) -> ToolResult:
        index_path = self.index_dir / f"{result_id}.json"
        if not index_path.exists():
            raise FileNotFoundError(f"工具结果索引不存在: {result_id}")
        data = json.loads(index_path.read_text(encoding="utf-8"))
        raw_path = data.get("raw_path")
        raw_result = Path(raw_path).read_text(encoding="utf-8") if raw_path else ""
        data["raw_result"] = raw_result
        return ToolResult(**data)

    def load_chunk(self, result_id: str, chunk_id: int) -> str:
        path = self.chunk_dir / f"{result_id}_chunk_{chunk_id}.txt"
        if not path.exists():
            raise FileNotFoundError(f"chunk 不存在: {result_id} #{chunk_id}")
        return path.read_text(encoding="utf-8")

    def search(self, result_id: str, keyword: str, top_k: int = 3) -> list[dict[str, Any]]:
        result = self.load(result_id)
        hits: list[dict[str, Any]] = []
        for chunk in result.chunks:
            text = self.load_chunk(result_id, int(chunk["chunk_id"]))
            if keyword.lower() in text.lower():
                preview = _preview_keyword(text, keyword)
                hits.append({"chunk_id": chunk["chunk_id"], "preview": preview})
                if len(hits) >= top_k:
                    break
        return hits

    def summarize(self, raw_result: str, tool_name: str) -> str:
        if tool_name == "log_analyzer":
            return _summarize_log(raw_result)
        if tool_name == "file_reader":
            return _summarize_file(raw_result)
        if tool_name == "csv_analyzer":
            return _summarize_csv(raw_result)
        if tool_name == "code_analyzer":
            return _summarize_code(raw_result)
        if tool_name == "repo_scanner":
            return _summarize_repo(raw_result)
        return _summarize_generic(raw_result)

    def list_results(self, task_id: str | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in sorted(self.index_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if task_id and data.get("metadata", {}).get("task_id") != task_id:
                continue
            rows.append(data)
        return rows

    def _write_chunks(self, result_id: str, content: str) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        if not content:
            return chunks
        for idx, start in enumerate(range(0, len(content), self.chunk_chars)):
            chunk_text = content[start : start + self.chunk_chars]
            path = self.chunk_dir / f"{result_id}_chunk_{idx}.txt"
            path.write_text(chunk_text, encoding="utf-8")
            chunks.append(
                {
                    "chunk_id": idx,
                    "path": str(path),
                    "char_len": len(chunk_text),
                    "token_len": estimate_tokens(chunk_text),
                }
            )
        return chunks


def _summarize_log(text: str, max_lines: int = 20) -> str:
    keywords = ["ERROR", "WARN", "OOM", "timeout", "failed", "exception", "KV cache"]
    lines = [
        line
        for line in text.splitlines()
        if any(keyword.lower() in line.lower() for keyword in keywords)
    ]
    selected = lines[:max_lines] or text.splitlines()[:8]
    return "\n".join(["日志摘要:", *selected, f"原始行数: {len(text.splitlines())}"])


def _summarize_file(text: str, max_lines: int = 12) -> str:
    lines = text.splitlines()
    return "\n".join(
        [
            "文件摘要:",
            f"总行数: {len(lines)}",
            f"估算 token: {estimate_tokens(text)}",
            "前几行:",
            *lines[:max_lines],
        ]
    )


def _summarize_csv(text: str) -> str:
    try:
        rows = list(csv.DictReader(text.splitlines()))
        columns = list(rows[0].keys()) if rows else []
        return f"CSV 摘要: 行数={len(rows)}, 列数={len(columns)}, 列名={columns}"
    except Exception:
        return _summarize_generic(text)


def _summarize_code(text: str) -> str:
    classes = len(re.findall(r"^\s*class\s+\w+", text, re.MULTILINE))
    funcs = len(re.findall(r"^\s*def\s+\w+", text, re.MULTILINE))
    imports = len(re.findall(r"^\s*(import|from)\s+", text, re.MULTILINE))
    todos = len(re.findall(r"TODO|FIXME", text, re.IGNORECASE))
    return f"代码摘要: class={classes}, function={funcs}, import={imports}, TODO/FIXME={todos}"


def _summarize_repo(text: str) -> str:
    lines = text.splitlines()
    interesting = [
        line
        for line in lines
        if any(key in line for key in ["README", "pyproject", "agentmem", "benchmarks", "scripts"])
    ][:20]
    return "\n".join(["仓库摘要:", f"条目数: {len(lines)}", *interesting])


def _summarize_generic(text: str, max_chars: int = 800) -> str:
    clean = " ".join(text.split())
    if len(clean) <= max_chars:
        return clean
    return clean[:max_chars] + "..."


def _preview_keyword(text: str, keyword: str, context_chars: int = 160) -> str:
    index = text.lower().find(keyword.lower())
    if index < 0:
        return text[:context_chars]
    start = max(0, index - context_chars // 2)
    end = min(len(text), index + context_chars // 2)
    return text[start:end]


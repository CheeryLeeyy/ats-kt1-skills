#!/usr/bin/env python3
"""Build model-principle JSON by reusing verified test-document input/output data."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def content_summary(item: dict) -> str:
    parts = [str(item.get("description", "")).strip()]
    content = item.get("content")
    if isinstance(content, dict) and content.get("type") == "table":
        rows = content.get("rows") or []
        snippets = [" / ".join(str(value) for value in row) for row in rows[:4]]
        if snippets:
            parts.append("主要内容：" + "；".join(snippets))
    elif isinstance(content, dict) and content.get("type") == "code":
        lines = [line.strip() for line in str(content.get("text", "")).splitlines() if line.strip()]
        if lines:
            parts.append("主要内容：" + "；".join(lines[:4]))
    return " ".join(part for part in parts if part)


def require_text(data: dict, key: str) -> str:
    value = str(data.get(key, "")).strip()
    if not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--names", required=True, type=Path)
    parser.add_argument("--test-data-dir", required=True, type=Path)
    parser.add_argument("--spec-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    names = json.loads(args.names.read_text(encoding="utf-8"))["algorithms"]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    test_paths = sorted(
        args.test_data_dir.glob("algo1-4-j-*.json"),
        key=lambda path: int(path.stem.rsplit("-", 1)[1]),
    )
    if not test_paths:
        raise ValueError("no test-document JSON files found")

    for test_path in test_paths:
        test_data = json.loads(test_path.read_text(encoding="utf-8"))
        package = require_text(test_data, "package_name")
        algorithm_id = require_text(test_data, "algorithm_id")
        if algorithm_id not in names:
            raise ValueError(f"latest-name mapping is missing {algorithm_id}")
        current_name = require_text(names[algorithm_id], "current_name")
        if require_text(test_data, "algorithm_name") != current_name:
            raise ValueError(f"{package} test data does not yet use the latest model name")

        spec_path = args.spec_dir / f"{package}.json"
        if not spec_path.is_file():
            raise ValueError(f"model-principle spec is missing: {spec_path}")
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        intro = spec.get("intro_paragraphs")
        nodes = spec.get("framework_nodes")
        flow_steps = spec.get("flow_steps")
        if not isinstance(intro, list):
            raise ValueError(f"{package} requires a list of introduction paragraphs")
        intro = [str(value).strip() for value in intro if str(value).strip()]
        if len(intro) < 4:
            raise ValueError(f"{package} requires at least four introduction paragraphs")
        if len("".join(intro)) < 350:
            raise ValueError(f"{package} introduction must contain at least 350 characters")
        if not isinstance(nodes, list) or len(nodes) != 6:
            raise ValueError(f"{package} requires exactly six framework nodes")
        nodes = [str(value).strip() for value in nodes]
        for node in nodes:
            separator = "：" if "：" in node else ":" if ":" in node else ""
            if not separator:
                raise ValueError(f"{package} framework node needs 模块名：作用说明: {node}")
            name, detail = (part.strip() for part in node.split(separator, 1))
            if not name or len(detail) < 6:
                raise ValueError(f"{package} framework node description is too short: {node}")
        if not isinstance(flow_steps, list) or len(flow_steps) != 6:
            raise ValueError(f"{package} requires exactly six detailed flow steps")
        flow_steps = [str(value).strip() for value in flow_steps]
        if any(len(value) < 12 for value in flow_steps):
            raise ValueError(f"{package} flow steps must explain data processing in detail")
        normalized_flow = [
            re.sub(r"^步骤\s*\d+\s*[：:]\s*", "", value).strip() for value in flow_steps
        ]
        if normalized_flow == nodes or set(normalized_flow) == set(nodes):
            raise ValueError(f"{package} flow steps must not duplicate or reorder framework nodes")
        if not any(token in normalized_flow[0] for token in ("输入", "读取", "接收", "加载")):
            raise ValueError(f"{package} first flow step must start from input data")
        if not any(token in normalized_flow[-1] for token in ("输出", "写入", "保存", "生成")):
            raise ValueError(f"{package} last flow step must produce the output data")
        for key in ("upstream_model_id", "downstream_model_id", "delivery_time"):
            if str(spec.get(key, "")).strip():
                raise ValueError(f"{package} {key} must stay blank per template comments")

        inputs = [
            {"name": item["name"], "detail": content_summary(item)}
            for item in test_data["input_files"]
        ]
        outputs = [
            {"name": item["name"], "detail": item["description"]}
            for item in test_data["output_files"]
        ]
        result = {
            "algorithm_id": algorithm_id,
            "package_name": package,
            "algorithm_name": current_name,
            "project_name": spec.get("project_name", "自主式交通系统跨域计算与决策优化"),
            "topic_name": spec.get("topic_name", "端边云协同的多方式自主交通系统全域认知计算"),
            "function_description": require_text(spec, "function_description"),
            "input_summary": "输入文件及其字段与对应测试说明保持一致，主要包括：" + "、".join(item["name"] for item in inputs) + "。",
            "inputs": inputs,
            "output_summary": "模型运行后输出文件及其字段与对应测试说明保持一致，主要包括：" + "、".join(item["name"] for item in outputs) + "。",
            "outputs": outputs,
            "service_scene": require_text(spec, "service_scene"),
            "upstream_model_id": "",
            "downstream_model_id": "",
            "delivery_time": "",
            "responsible_unit": str(spec.get("responsible_unit", "北京邮电大学")),
            "intro_paragraphs": intro,
            "framework_nodes": nodes,
            "flow_steps": flow_steps,
        }
        output = args.output_dir / f"{package}.json"
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

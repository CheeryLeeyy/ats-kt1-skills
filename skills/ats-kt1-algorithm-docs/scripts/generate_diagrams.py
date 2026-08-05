#!/usr/bin/env python3
"""Draw algorithm-specific framework and flow diagrams as original SVG artwork."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path


def wrap(text: str, width: int) -> list[str]:
    units = re.findall(r"[A-Za-z0-9_.<>/—-]+|.", text)
    lines: list[str] = []
    current = ""
    for unit in units:
        if len(current) + len(unit) <= width:
            current += unit
            continue
        if current:
            lines.append(current)
        if len(unit) <= width:
            current = unit
        else:
            lines.extend(unit[index : index + width] for index in range(0, len(unit), width))
            current = ""
    if current:
        lines.append(current)
    return lines or [""]


def text_lines(text: str, x: int, y: int, width: int, line_height: int = 26, size: int = 22) -> str:
    lines = wrap(text, width)
    start = y - (len(lines) - 1) * line_height // 2
    spans = "".join(
        f'<tspan x="{x}" y="{start + index * line_height}">{html.escape(line)}</tspan>'
        for index, line in enumerate(lines)
    )
    return f'<text text-anchor="middle" font-family="Noto Sans CJK SC, Microsoft YaHei, sans-serif" font-size="{size}" fill="#17324d">{spans}</text>'


def compact_name(value: str, width: int = 24) -> str:
    value = str(value)
    if len(value) <= width:
        return value
    tail = value.rsplit("/", 1)[-1]
    prefix = "test_dataset/…/" if value.startswith("test_dataset/") else "…/"
    candidate = prefix + tail
    if len(candidate) <= width:
        return candidate
    keep = max(6, (width - 1) // 2)
    return tail[:keep] + "…" + tail[-keep:]


def compact_items(items: list[dict], limit: int = 2) -> str:
    labels = [compact_name(item["name"]) for item in items[:limit]]
    if len(items) > limit:
        labels.append(f"等{len(items)}项")
    return "、".join(labels)


def input_output_text(data: dict) -> str:
    inputs = compact_items(data["inputs"])
    outputs = compact_items(data["outputs"])
    return f"输入：{inputs}；输出：{outputs}"


def framework(data: dict) -> str:
    nodes = data["framework_nodes"]
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="520" viewBox="0 0 1200 520">',
        '<rect width="1200" height="520" fill="white"/>',
        '<defs><marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="4" orient="auto"><path d="M0,0 L0,8 L11,4 z" fill="#3976b8"/></marker></defs>',
        f'<text x="600" y="42" text-anchor="middle" font-family="Noto Sans CJK SC, Microsoft YaHei, sans-serif" font-size="24" font-weight="bold" fill="#17324d">{html.escape(data["algorithm_id"])} 算法模型框架</text>',
        text_lines(input_output_text(data), 600, 76, 52, line_height=18, size=15),
    ]
    positions = [(80, 110), (410, 110), (740, 110), (740, 335), (410, 335), (80, 335)]
    centers = [(x + 145, y + 70) for x, y in positions]
    colors = ["#eaf2ff", "#edf8f2", "#fff4df", "#f3edff", "#eaf7fb", "#f8eff1"]
    for index, ((x, y), node) in enumerate(zip(positions, nodes)):
        parts.append(f'<rect x="{x}" y="{y}" width="290" height="140" rx="18" fill="{colors[index]}" stroke="#3976b8" stroke-width="3"/>')
        parts.append(text_lines(node, x + 145, y + 76, 10))
    for (x1, y1), (x2, y2) in zip(centers, centers[1:]):
        if y1 == y2:
            sx = x1 + (145 if x2 > x1 else -145)
            ex = x2 - (145 if x2 > x1 else -145)
            parts.append(f'<path d="M{sx},{y1} L{ex},{y2}" stroke="#3976b8" stroke-width="4" fill="none" marker-end="url(#arrow)"/>')
        else:
            parts.append(f'<path d="M{x1},{y1 + 70} L{x2},{y2 - 70}" stroke="#3976b8" stroke-width="4" fill="none" marker-end="url(#arrow)"/>')
    parts.append('</svg>')
    return "".join(parts)


def flow(data: dict) -> str:
    steps = data["flow_steps"]
    height = 1060
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="{height}" viewBox="0 0 900 {height}">',
        f'<rect width="900" height="{height}" fill="white"/>',
        '<defs><marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="4" orient="auto"><path d="M0,0 L0,8 L11,4 z" fill="#3976b8"/></marker></defs>',
        f'<text x="450" y="42" text-anchor="middle" font-family="Noto Sans CJK SC, Microsoft YaHei, sans-serif" font-size="25" font-weight="bold" fill="#17324d">{html.escape(data["algorithm_id"])} 算法模型流程</text>',
        text_lines(input_output_text(data), 450, 72, 42, line_height=18, size=15),
    ]
    top = 110
    for index, step in enumerate(steps):
        y = top + index * 155
        fill = "#eaf2ff" if index % 2 == 0 else "#edf8f2"
        parts.append(f'<rect x="150" y="{y}" width="600" height="105" rx="18" fill="{fill}" stroke="#3976b8" stroke-width="3"/>')
        parts.append(text_lines(step, 450, y + 58, 22, line_height=28, size=22))
        if index < len(steps) - 1:
            parts.append(f'<path d="M450,{y + 108} L450,{y + 145}" stroke="#3976b8" stroke-width="4" marker-end="url(#arrow)"/>')
    parts.append('</svg>')
    return "".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="keep extracted PNG/SVG diagrams and generate only missing kinds",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(args.data_dir.glob("algo1-4-j-*.json"), key=lambda p: int(p.stem.rsplit("-", 1)[1])):
        data = json.loads(path.read_text(encoding="utf-8"))
        for kind, payload in (("framework", framework(data)), ("flow", flow(data))):
            existing_png = args.output_dir / f"{data['package_name']}-{kind}.png"
            output = args.output_dir / f"{data['package_name']}-{kind}.svg"
            if args.missing_only and (existing_png.is_file() or output.is_file()):
                print(f"reused: {existing_png if existing_png.is_file() else output}")
                continue
            output.write_text(payload + "\n", encoding="utf-8")
            print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

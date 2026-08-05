#!/usr/bin/env python3
"""Extract framework and flow diagrams embedded in an existing model DOCX."""

from __future__ import annotations

import argparse
import base64
import json
import posixpath
import re
import struct
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"
KEYWORDS = {
    "framework": ("算法框架图", "模型框架图", "算法框架", "模型框架", "架构图"),
    "flow": ("算法模型流程图", "算法流程图", "模型流程图", "流程图", "处理流程"),
}
MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


def paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(W + "t")).strip()


def classify(paragraphs: list[ET.Element], index: int) -> tuple[str | None, int, str]:
    best_kind = None
    best_score = -1
    best_context = ""
    for nearby_index, paragraph in enumerate(paragraphs):
        distance = abs(nearby_index - index)
        if distance > 8:
            continue
        value = paragraph_text(paragraph)
        normalized = re.sub(r"^\d+(?:\.\d+)*\s*", "", value).strip()
        for kind, keywords in KEYWORDS.items():
            if any(keyword in value for keyword in keywords):
                score = 100 - distance * 8
                if normalized in keywords:
                    score += 20
                if score > best_score:
                    best_kind = kind
                    best_score = score
                    best_context = value
    return best_kind, best_score, best_context


def image_size(data: bytes, suffix: str) -> tuple[int, int]:
    if suffix == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    return 1000, 1000


def svg_wrapper(data: bytes, mime_type: str, width: int, height: int) -> bytes:
    encoded = base64.b64encode(data).decode("ascii")
    value = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="white"/>'
        f'<image width="{width}" height="{height}" preserveAspectRatio="xMidYMid meet" '
        f'href="data:{mime_type};base64,{encoded}"/></svg>\n'
    )
    return value.encode("utf-8")


def write_diagram(output_dir: Path, package: str, kind: str, member: str, data: bytes) -> list[str]:
    suffix = Path(member).suffix.lower()
    outputs: list[Path] = []
    if suffix == ".svg":
        output = output_dir / f"{package}-{kind}.svg"
        output.write_bytes(data)
        outputs.append(output)
    elif suffix in MIME_TYPES:
        width, height = image_size(data, suffix)
        if suffix == ".png":
            output = output_dir / f"{package}-{kind}.png"
            output.write_bytes(data)
            outputs.append(output)
            if kind != "flow":
                return [str(path) for path in outputs]
        wrapper = output_dir / f"{package}-{kind}.svg"
        wrapper.write_bytes(svg_wrapper(data, MIME_TYPES[suffix], width, height))
        outputs.append(wrapper)
    else:
        raise ValueError(f"unsupported embedded image format: {member}")
    return [str(path) for path in outputs]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docx", required=True, type=Path)
    parser.add_argument("--package", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(args.docx) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
        relationships = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
        targets = {
            item.get("Id", ""): item.get("Target", "")
            for item in relationships.iter(PR + "Relationship")
        }
        paragraphs = list(document.iter(W + "p"))
        candidates = []
        for index, paragraph in enumerate(paragraphs):
            relationship_ids = [
                node.get(R + "embed", "") for node in paragraph.iter(A + "blip")
            ]
            relationship_ids = [value for value in relationship_ids if value in targets]
            if not relationship_ids:
                continue
            kind, score, context = classify(paragraphs, index)
            members = []
            for relationship_id in relationship_ids:
                target = targets[relationship_id].lstrip("/")
                member = posixpath.normpath(
                    target if target.startswith("word/") else posixpath.join("word", target)
                )
                if member.startswith("word/media/") and member in archive.namelist():
                    members.append(member)
            if members:
                members.sort(key=lambda value: (Path(value).suffix.lower() != ".svg", value))
                candidates.append(
                    {
                        "index": index,
                        "kind": kind,
                        "score": score,
                        "context": context,
                        "member": members[0],
                    }
                )

        classified = [item for item in candidates if item["kind"]]
        if len(candidates) == 2 and len(classified) < 2:
            for kind, item in zip(("framework", "flow"), candidates):
                if not item["kind"]:
                    item["kind"] = kind
                    item["score"] = 1
                    item["context"] = "inferred from two-image document order"

        selected = {}
        for item in candidates:
            kind = item["kind"]
            if not kind:
                continue
            if kind not in selected or item["score"] > selected[kind]["score"]:
                selected[kind] = item

        found = {}
        for kind, item in selected.items():
            data = archive.read(item["member"])
            outputs = write_diagram(args.output_dir, args.package, kind, item["member"], data)
            found[kind] = {**item, "outputs": outputs}

    payload = {
        "source": str(args.docx),
        "package": args.package,
        "review_required": True,
        "found": found,
        "missing": [kind for kind in ("framework", "flow") if kind not in found],
        "candidates": candidates,
        "unclassified": [item for item in candidates if not item["kind"]],
    }
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(args.manifest)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Extract DOCX comments and their anchored text without external dependencies."""

from __future__ import annotations

import argparse
import json
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def node_text(node: ET.Element) -> str:
    return "".join(item.text or "" for item in node.iter(W + "t")).strip()


def extract_comments(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        comments_root = ET.fromstring(archive.read("word/comments.xml"))
        document_root = ET.fromstring(archive.read("word/document.xml"))

    comments = {
        comment.get(W + "id", ""): node_text(comment)
        for comment in comments_root.iter(W + "comment")
    }
    anchors: dict[str, list[str]] = defaultdict(list)
    active: set[str] = set()

    def visit(node: ET.Element) -> None:
        if node.tag == W + "commentRangeStart":
            active.add(node.get(W + "id", ""))
        elif node.tag == W + "commentRangeEnd":
            active.discard(node.get(W + "id", ""))
        elif node.tag == W + "t" and node.text:
            for comment_id in active:
                anchors[comment_id].append(node.text)
        for child in node:
            visit(child)

    visit(document_root)
    return [
        {
            "id": comment_id,
            "anchor": "".join(anchors.get(comment_id, [])).strip(),
            "comment": comment,
        }
        for comment_id, comment in sorted(comments.items(), key=lambda item: int(item[0]))
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docx", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="optional JSON output")
    args = parser.parse_args()
    result = extract_comments(args.docx)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
        print(args.output)
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

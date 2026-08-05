#!/usr/bin/env python3
"""Validate model-principle documents against naming, template, and content rules."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
FORBIDDEN_INTRO_NAMES = ("HierFL", "PointPillar", "DJSCC", "PILoRA", "VAE", "MFE", "SRE", "AQC", "Enhancing Communication", "ASC-CP")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docx", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--old-name", default="")
    args = parser.parse_args()
    data = json.loads(args.data.read_text(encoding="utf-8"))
    errors: list[str] = []
    expected = f"{data['package_name']}模型原理说明.docx"
    if args.docx.name != expected:
        errors.append(f"filename mismatch: {args.docx.name} != {expected}")
    try:
        with zipfile.ZipFile(args.docx) as archive:
            if archive.testzip():
                errors.append("corrupt ZIP member")
            names = set(archive.namelist())
            if any("comments" in name.lower() or name.lower().endswith("word/people.xml") for name in names):
                errors.append("comment metadata remains")
            for required_media in ("word/media/image1.png", "word/media/image2.png", "word/media/image3.svg"):
                if required_media not in names:
                    errors.append(f"missing diagram media: {required_media}")
            xml = archive.read("word/document.xml")
    except Exception as exc:
        errors.append(f"cannot open DOCX: {exc}")
        xml = b""
    if xml:
        if b"Ignorable=" in xml or b"w14:" in xml:
            errors.append("Word compatibility markup remains")
        root = ET.fromstring(xml)
        paragraphs = ["".join(t.text or "" for t in p.iter(W + "t")) for p in root.iter(W + "p")]
        body_text = "\n".join(paragraphs)
        for heading in ("1 算法模型基本信息", "2 算法模型简介", "算法框架图", "3 算法模型流程图"):
            if heading not in paragraphs:
                errors.append(f"missing heading/caption: {heading}")
        for value in (data["algorithm_id"], data["algorithm_name"]):
            if value not in body_text:
                errors.append(f"missing required value: {value}")
        if args.old_name and args.old_name != data["algorithm_name"] and args.old_name in body_text:
            errors.append(f"old model name remains: {args.old_name}")
        other_ids = set(re.findall(r"1-4-J-\d+", body_text)) - {data["algorithm_id"]}
        if other_ids:
            errors.append(f"other algorithm identifiers remain: {sorted(other_ids)}")
        for item in data["inputs"] + data["outputs"]:
            if item["name"] not in body_text:
                errors.append(f"input/output missing: {item['name']}")
        start = paragraphs.index("2 算法模型简介") + 1 if "2 算法模型简介" in paragraphs else 0
        end = paragraphs.index("算法框架图") if "算法框架图" in paragraphs else len(paragraphs)
        intro_paragraphs = [value for value in paragraphs[start:end] if value.strip()]
        if len(intro_paragraphs) < 4:
            errors.append(f"model introduction too short: {len(intro_paragraphs)} paragraphs")
        intro_text = "".join(intro_paragraphs)
        if len(intro_text) < 350:
            errors.append(f"model introduction too brief: {len(intro_text)} characters")
        for forbidden in FORBIDDEN_INTRO_NAMES:
            if forbidden in intro_text:
                errors.append(f"forbidden original English method/module name in introduction: {forbidden}")
        if sum(1 for _ in root.iter(W + "drawing")) != 2:
            errors.append("expected exactly two self-drawn diagrams")
        tables = list(root.iter(W + "tbl"))
        if len(tables) != 1:
            errors.append(f"expected one basic-information table, found {len(tables)}")
        elif len(list(tables[0].iter(W + "tr"))) < 15:
            errors.append("basic-information table is missing detailed input/output rows")
        for label in ("上游接口模型编号", "下游接口模型编号", "交付时间"):
            if label not in body_text:
                errors.append(f"blank template field label missing: {label}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"OK: {args.docx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

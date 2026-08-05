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
FORBIDDEN_ENGLISH_NAMES = ("HierFL", "PointPillar", "DJSCC", "PILoRA", "VAE", "MFE", "SRE", "AQC", "Enhancing Communication", "ASC-CP", "DEVA")
ALLOWED_ENGLISH_TERMS = {"CPU", "GPU", "JSON", "CSV", "NPY", "NPZ", "V2V", "V2X", "Docker"}
UNRELATED_TERMS = ("小猫", "小狗", "猫咪", "宠物")


def element_text(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.iter(W + "t")).strip()


def vertical_merge_value(cell: ET.Element) -> str | None:
    marker = cell.find(f"{W}tcPr/{W}vMerge")
    if marker is None:
        return None
    return marker.get(W + "val", "continue")


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
        for marker in (W + "commentRangeStart", W + "commentRangeEnd", W + "commentReference"):
            if any(True for _ in root.iter(marker)):
                errors.append(f"comment anchor remains: {marker.rsplit('}', 1)[-1]}")
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
        diagram_text = "".join(str(value) for value in data.get("framework_nodes", [])) + "".join(
            str(value) for value in data.get("flow_steps", [])
        )
        reviewed_text = intro_text
        for forbidden in FORBIDDEN_ENGLISH_NAMES:
            if forbidden.casefold() in reviewed_text.casefold():
                errors.append(f"forbidden original English method/module name in body text: {forbidden}")
        english_terms = {
            value
            for value in re.findall(r"\b[A-Za-z][A-Za-z0-9-]{2,}\b", reviewed_text)
            if value not in ALLOWED_ENGLISH_TERMS
        }
        if english_terms:
            errors.append(f"possible English method/module names remain: {sorted(english_terms)}")
        for term in UNRELATED_TERMS:
            if term in body_text or term in diagram_text:
                errors.append(f"traffic-unrelated example remains: {term}")
        if sum(1 for _ in root.iter(W + "drawing")) != 2:
            errors.append("expected exactly two embedded diagrams")
        tables = list(root.iter(W + "tbl"))
        if len(tables) != 1:
            errors.append(f"expected one basic-information table, found {len(tables)}")
        elif len(list(tables[0].iter(W + "tr"))) < 15:
            errors.append("basic-information table is missing detailed input/output rows")
        blank_labels = ("上游接口模型编号", "下游接口模型编号", "交付时间")
        for label in blank_labels:
            if label not in body_text:
                errors.append(f"blank template field label missing: {label}")
        if tables:
            values_by_label = {}
            rows = list(tables[0].iter(W + "tr"))
            for row in rows:
                cells = list(row.findall(W + "tc"))
                if len(cells) == 2:
                    values_by_label[element_text(cells[0])] = element_text(cells[1])
            for label in blank_labels:
                if values_by_label.get(label, "").strip():
                    errors.append(f"template field must stay blank: {label}")

            row_labels = [element_text(list(row.findall(W + "tc"))[0]) for row in rows]
            for label, next_label in (("输入数据要求", "输出数据要求"), ("输出数据要求", "模型服务场景")):
                if label not in row_labels or next_label not in row_labels:
                    errors.append(f"cannot inspect vertically merged table group: {label}")
                    continue
                start_index = row_labels.index(label)
                end_index = row_labels.index(next_label)
                group = rows[start_index:end_index]
                if len(group) < 2:
                    errors.append(f"{label} has no detailed file rows")
                    continue
                first_cells = [list(row.findall(W + "tc"))[0] for row in group]
                if vertical_merge_value(first_cells[0]) != "restart":
                    errors.append(f"{label} label cell does not start a vertical merge")
                if any(vertical_merge_value(cell) != "continue" for cell in first_cells[1:]):
                    errors.append(f"{label} label cell does not span all detailed file rows")

        nodes = [str(value).strip() for value in data.get("framework_nodes", [])]
        if len(nodes) != 6 or any(("：" not in value and ":" not in value) for value in nodes):
            errors.append("framework nodes must contain six 模块名：作用说明 items")
        flow_steps = [str(value).strip() for value in data.get("flow_steps", [])]
        if len(flow_steps) != 6 or any(len(value) < 12 for value in flow_steps):
            errors.append("flow diagram must contain six detailed data-processing steps")
        else:
            normalized_flow = [
                re.sub(r"^步骤\s*\d+\s*[：:]\s*", "", value).strip()
                for value in flow_steps
            ]
            if normalized_flow == nodes or set(normalized_flow) == set(nodes):
                errors.append("flow diagram duplicates or reorders framework nodes")
            if not any(token in normalized_flow[0] for token in ("输入", "读取", "接收", "加载")):
                errors.append("flow diagram does not start from input data")
            if not any(token in normalized_flow[-1] for token in ("输出", "写入", "保存", "生成")):
                errors.append("flow diagram does not finish with output data")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"OK: {args.docx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

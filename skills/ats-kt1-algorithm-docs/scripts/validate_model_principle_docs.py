#!/usr/bin/env python3
"""Validate model-principle documents against naming, template, and content rules."""

from __future__ import annotations

import argparse
import json
import re
import struct
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
ASVG = "{http://schemas.microsoft.com/office/drawing/2016/SVG/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
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


def png_dimensions(payload: bytes) -> tuple[int, int]:
    if payload[:8] != b"\x89PNG\r\n\x1a\n" or payload[12:16] != b"IHDR":
        raise ValueError("embedded diagram is not a supported PNG")
    return struct.unpack(">II", payload[16:24])


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
            for required_media in ("word/media/image1.png", "word/media/image2.png"):
                if required_media not in names:
                    errors.append(f"missing diagram media: {required_media}")
            if any(name.lower().endswith(".svg") for name in names):
                errors.append("SVG alternate diagram remains; Word may bypass the verified PNG")
            xml = archive.read("word/document.xml")
            media_payloads = [
                archive.read(name)
                for name in ("word/media/image1.png", "word/media/image2.png")
                if name in names
            ]
    except Exception as exc:
        errors.append(f"cannot open DOCX: {exc}")
        xml = b""
        media_payloads = []
    if xml:
        if b"Ignorable=" in xml or b"w14:" in xml:
            errors.append("Word compatibility markup remains")
        root = ET.fromstring(xml)
        if any(True for _ in root.iter(A + "srcRect")):
            errors.append("diagram crop metadata remains")
        if any(True for _ in root.iter(ASVG + "svgBlip")):
            errors.append("SVG alternate diagram reference remains")
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
            if not str(item.get("file_description", "")).strip():
                errors.append(f"file-level Chinese description missing: {item['name']}")
            elif item["file_description"] not in body_text:
                errors.append(f"file-level description not written: {item['name']}")
            fields = item.get("fields")
            if not isinstance(fields, list) or not fields:
                errors.append(f"field-level details missing: {item['name']}")
                continue
            for field in fields:
                for key in ("name", "type", "description", "content"):
                    value = str(field.get(key, "")).strip() if isinstance(field, dict) else ""
                    if not value:
                        errors.append(f"{item['name']} field {key} is empty")
                    elif value not in body_text:
                        errors.append(f"{item['name']} field {key} not written: {value}")
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
        drawing_extents = []
        for drawing in root.iter(W + "drawing"):
            extent = drawing.find(f".//{WP}extent")
            if extent is not None:
                drawing_extents.append((int(extent.get("cx", "0")), int(extent.get("cy", "0"))))
        if len(drawing_extents) == 2 and len(media_payloads) == 2:
            for index, ((cx, cy), payload) in enumerate(zip(drawing_extents, media_payloads), 1):
                width, height = png_dimensions(payload)
                if not cx or not cy or abs((cx / cy) / (width / height) - 1) > 0.01:
                    errors.append(f"diagram {index} display aspect ratio does not match embedded image")
        tables = list(root.iter(W + "tbl"))
        if len(tables) != 1:
            errors.append(f"expected one basic-information table, found {len(tables)}")
        obsolete_labels = ("上游接口模型编号", "下游接口模型编号", "交付时间")
        for label in obsolete_labels:
            if label in body_text:
                errors.append(f"obsolete template field remains: {label}")
        if tables:
            table_text = element_text(tables[0])
            runtime_items = [
                item for item in data["inputs"] + data["outputs"]
                if item.get("runtime_only") or str(item.get("role", "")).strip().lower() == "docker-runtime"
            ]
            if runtime_items:
                errors.append("Docker runtime configuration items must not enter model input/output data")
            values_by_label = {}
            rows = list(tables[0].iter(W + "tr"))
            for row in rows:
                cells = list(row.findall(W + "tc"))
                if len(cells) == 2:
                    values_by_label[element_text(cells[0])] = element_text(cells[1])
            expected_scenarios = "，".join(data.get("supported_scenarios", []))
            if values_by_label.get("支持的协同场景", "").strip() != expected_scenarios:
                errors.append("supported collaboration scenes do not match workbook columns C-F")
            if body_text.count("支持的协同场景") != 1:
                errors.append("supported collaboration scene row must appear exactly once")

            row_labels = [element_text(list(row.findall(W + "tc"))[0]) for row in rows]
            groups = (
                ("输入数据要求", "输出数据要求", data["inputs"]),
                ("输出数据要求", "模型服务场景", data["outputs"]),
            )
            for label, next_label, items in groups:
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
                expected_rows = 1 + sum(len(item.get("fields", [])) for item in items)
                if len(group) != expected_rows:
                    errors.append(f"{label} row count mismatch: {len(group)} != {expected_rows}")
                    continue
                if len(list(group[0].findall(W + "tc"))) != 2:
                    errors.append(f"{label} summary row must span the file and field columns")
                cursor = 1
                for item in items:
                    if re.search(r"[（(][^（）()]*[）)]", str(item.get("file_description", ""))):
                        errors.append(f"{item['name']} file description must use a direct Chinese name without parenthetical qualifiers")
                    fields = item.get("fields", [])
                    file_rows = group[cursor : cursor + len(fields)]
                    cursor += len(fields)
                    if any(len(list(row.findall(W + "tc"))) != 3 for row in file_rows):
                        errors.append(f"{label} {item['name']} requires three-column field rows")
                        continue
                    middle_cells = [list(row.findall(W + "tc"))[1] for row in file_rows]
                    if len(fields) == 1:
                        if vertical_merge_value(middle_cells[0]) is not None:
                            errors.append(f"{item['name']} single field row must not merge into the next file")
                    else:
                        if vertical_merge_value(middle_cells[0]) != "restart":
                            errors.append(f"{item['name']} file cell does not start a vertical merge")
                        if any(vertical_merge_value(cell) != "continue" for cell in middle_cells[1:]):
                            errors.append(f"{item['name']} file cell does not span all of its fields")
                    expected_file_text = f"{item['file_description']}{item['name']}"
                    if element_text(middle_cells[0]) != expected_file_text:
                        errors.append(f"{item['name']} file cell must contain Chinese description and filename")
                    for index, (row, field) in enumerate(zip(file_rows, fields)):
                        cells = list(row.findall(W + "tc"))
                        if index and element_text(cells[1]):
                            errors.append(f"{item['name']} merged continuation cell must stay empty")
                        if vertical_merge_value(cells[2]) is not None:
                            errors.append(f"{item['name']} field cells must remain individually separated")
                        field_text = element_text(cells[2])
                        for key in ("description", "name", "type", "content"):
                            if str(field[key]) not in field_text:
                                errors.append(f"{item['name']} field row omits {key}: {field['name']}")

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

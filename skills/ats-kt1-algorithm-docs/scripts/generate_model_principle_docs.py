#!/usr/bin/env python3
"""Generate model-principle DOCX files from the approved commented template."""

from __future__ import annotations

import argparse
import json
import os
import struct
import tempfile
import zipfile
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
XML_NS = "http://www.w3.org/XML/1998/namespace"
W = f"{{{W_NS}}}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
ASVG = "{http://schemas.microsoft.com/office/drawing/2016/SVG/main}"
PROJECT_NAME = "自主式交通系统端-边-云协同计算架构与基础算法模型"
TOPIC_NAME = "协同计算性能增强导向的传算融合基础算法"


def register_namespaces(xml_bytes: bytes) -> None:
    for _, pair in ET.iterparse(BytesIO(xml_bytes), events=("start-ns",)):
        prefix, uri = pair
        if prefix not in {"xml", "xmlns"}:
            ET.register_namespace(prefix, uri)


def text(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.iter(W + "t"))


def first_run_properties(element: ET.Element) -> ET.Element | None:
    run = element.find(f".//{W}r")
    if run is None:
        return None
    props = run.find(W + "rPr")
    return deepcopy(props) if props is not None else None


def append_text(run: ET.Element, value: str) -> None:
    pieces = str(value).split("\n")
    for index, piece in enumerate(pieces):
        if index:
            ET.SubElement(run, W + "br")
        node = ET.SubElement(run, W + "t")
        if piece.startswith(" ") or piece.endswith(" "):
            node.set(f"{{{XML_NS}}}space", "preserve")
        node.text = piece


def clone_paragraph(sample: ET.Element, value: str) -> ET.Element:
    result = deepcopy(sample)
    props = result.find(W + "pPr")
    for child in list(result):
        if child is not props:
            result.remove(child)
    run = ET.SubElement(result, W + "r")
    run_props = first_run_properties(sample)
    if run_props is not None:
        run.append(run_props)
    append_text(run, value)
    return result


def replace_cell_text(cell: ET.Element, value: str) -> None:
    sample_p = cell.find(W + "p")
    if sample_p is None:
        sample_p = ET.Element(W + "p")
    for child in list(cell):
        if child.tag != W + "tcPr":
            cell.remove(child)
    cell.append(clone_paragraph(sample_p, value))


def table_row(sample: ET.Element, values: list[str]) -> ET.Element:
    result = deepcopy(sample)
    cells = result.findall(W + "tc")
    if len(cells) != len(values):
        raise ValueError(f"sample table row has {len(cells)} cells; expected {len(values)}")
    for cell, value in zip(cells, values):
        replace_cell_text(cell, value)
    row_props = result.find(W + "trPr")
    if row_props is None:
        row_props = ET.Element(W + "trPr")
        result.insert(0, row_props)
    for marker in list(row_props.findall(W + "cantSplit")):
        row_props.remove(marker)
    row_props.insert(0, ET.Element(W + "cantSplit"))
    return result


def set_vertical_merge(cell: ET.Element, *, restart: bool) -> None:
    """Merge one label cell vertically across its following detail rows."""
    props = cell.find(W + "tcPr")
    if props is None:
        props = ET.Element(W + "tcPr")
        cell.insert(0, props)
    for marker in list(props.findall(W + "vMerge")):
        props.remove(marker)
    marker = ET.SubElement(props, W + "vMerge")
    if restart:
        marker.set(W + "val", "restart")


def clear_vertical_merge(cell: ET.Element) -> None:
    props = cell.find(W + "tcPr")
    if props is None:
        return
    for marker in list(props.findall(W + "vMerge")):
        props.remove(marker)


def short_name(value: object) -> str:
    """Return a display name without Docker or host directory components."""
    normalized = str(value).strip().replace("\\", "/").rstrip("/")
    return normalized.rsplit("/", 1)[-1]


def file_cell_text(item: dict) -> str:
    return f"{item['file_description']}\n{short_name(item['name'])}"


def field_cell_text(field: dict) -> str:
    return f"{field['description']}\n{short_name(field['name'])} ({field['type']})"


def build_table(sample: ET.Element, data: dict) -> ET.Element:
    rows = sample.findall(W + "tr")
    metadata_sample = next(row for row in rows if len(row.findall(W + "tc")) == 2)
    detail_sample = next(row for row in rows if len(row.findall(W + "tc")) == 3)
    result = deepcopy(sample)
    for row in list(result.findall(W + "tr")):
        result.remove(row)

    metadata = [
        ("课题名称", PROJECT_NAME),
        ("专题名称", TOPIC_NAME),
        ("模型编号", data["algorithm_id"]),
        ("模型名称", data["algorithm_name"]),
        ("模型功能描述", data["function_description"]),
    ]
    for label, value in metadata:
        result.append(table_row(metadata_sample, [label, value]))

    input_summary_row = table_row(metadata_sample, ["输入数据要求", data["input_summary"]])
    set_vertical_merge(input_summary_row.findall(W + "tc")[0], restart=True)
    result.append(input_summary_row)
    for item in data["inputs"]:
        fields = item["fields"]
        for index, field in enumerate(fields):
            detail_row = table_row(
                detail_sample,
                ["", file_cell_text(item) if index == 0 else "", field_cell_text(field)],
            )
            cells = detail_row.findall(W + "tc")
            set_vertical_merge(cells[0], restart=False)
            clear_vertical_merge(cells[2])
            if len(fields) > 1:
                set_vertical_merge(cells[1], restart=index == 0)
            else:
                clear_vertical_merge(cells[1])
            result.append(detail_row)

    output_summary_row = table_row(metadata_sample, ["输出数据要求", data["output_summary"]])
    set_vertical_merge(output_summary_row.findall(W + "tc")[0], restart=True)
    result.append(output_summary_row)
    for item in data["outputs"]:
        fields = item["fields"]
        for index, field in enumerate(fields):
            detail_row = table_row(
                detail_sample,
                ["", file_cell_text(item) if index == 0 else "", field_cell_text(field)],
            )
            cells = detail_row.findall(W + "tc")
            set_vertical_merge(cells[0], restart=False)
            clear_vertical_merge(cells[2])
            if len(fields) > 1:
                set_vertical_merge(cells[1], restart=index == 0)
            else:
                clear_vertical_merge(cells[1])
            result.append(detail_row)
    for label, value in (
        ("模型服务场景", data["service_scene"]),
        ("支持的协同场景", data["supported_scenarios_text"]),
        ("责任单位", data["responsible_unit"]),
    ):
        result.append(table_row(metadata_sample, [label, value]))
    return result


def resize_drawing(paragraph: ET.Element, cx: str, cy: str) -> ET.Element:
    result = deepcopy(paragraph)
    for extent in result.iter(WP + "extent"):
        extent.set("cx", cx)
        extent.set("cy", cy)
    for transform in result.iter(A + "xfrm"):
        extent = transform.find(A + "ext")
        if extent is not None:
            extent.set("cx", cx)
            extent.set("cy", cy)
    for parent in result.iter():
        for crop in list(parent.findall(A + "srcRect")):
            parent.remove(crop)
    for extension_list in result.iter(A + "extLst"):
        for extension in list(extension_list):
            if any(True for _ in extension.iter(ASVG + "svgBlip")):
                extension_list.remove(extension)
    return result


def build_document(
    template_xml: bytes,
    data: dict,
    framework_extent: tuple[str, str],
    flow_extent: tuple[str, str],
) -> bytes:
    register_namespaces(template_xml)
    root = ET.fromstring(template_xml)
    body = root.find(W + "body")
    if body is None:
        raise ValueError("template has no body")
    blocks = list(body)
    paragraphs = [block for block in blocks if block.tag == W + "p"]
    tables = [block for block in blocks if block.tag == W + "tbl"]
    section = next(block for block in blocks if block.tag == W + "sectPr")
    title_sample = next(p for p in paragraphs if text(p).startswith("1-4-J-1"))
    h1_basic = next(p for p in paragraphs if text(p) == "1 算法模型基本信息")
    h1_intro = next(p for p in paragraphs if text(p) == "2 算法模型简介")
    normal_sample = next(p for p in paragraphs if text(p).startswith("该模型面向"))
    caption_sample = next(p for p in paragraphs if text(p) == "算法框架图")
    h1_flow = next(p for p in paragraphs if text(p) == "3 算法模型流程图")
    framework_drawing = next(p for p in paragraphs if any(blip.get(f"{{{R_NS}}}embed") == "rId8" for blip in p.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}blip")))
    flow_drawing = next(p for p in paragraphs if any(blip.get(f"{{{R_NS}}}embed") == "rId9" for blip in p.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}blip")))

    for child in list(body):
        body.remove(child)
    body.append(clone_paragraph(title_sample, f"{data['algorithm_id']} {data['algorithm_name']}"))
    body.append(clone_paragraph(h1_basic, "1 算法模型基本信息"))
    body.append(build_table(tables[0], data))
    body.append(clone_paragraph(normal_sample, ""))
    body.append(clone_paragraph(h1_intro, "2 算法模型简介"))
    for paragraph in data["intro_paragraphs"]:
        body.append(clone_paragraph(normal_sample, paragraph))
    body.append(resize_drawing(framework_drawing, *framework_extent))
    body.append(clone_paragraph(caption_sample, "算法框架图"))
    body.append(clone_paragraph(h1_flow, "3 算法模型流程图"))
    body.append(resize_drawing(flow_drawing, *flow_extent))
    body.append(deepcopy(section))

    root.attrib.pop(f"{{{MC_NS}}}Ignorable", None)
    for element in root.iter():
        for attribute in list(element.attrib):
            if attribute.startswith(f"{{{W14_NS}}}"):
                del element.attrib[attribute]
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def strip_relationships(payload: bytes) -> bytes:
    register_namespaces(payload)
    root = ET.fromstring(payload)
    for child in list(root):
        relation_type = child.get("Type", "").lower()
        target = child.get("Target", "").lower()
        if "comments" in relation_type or relation_type.endswith("/people") or target.endswith(".svg"):
            root.remove(child)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def strip_content_types(payload: bytes) -> bytes:
    register_namespaces(payload)
    root = ET.fromstring(payload)
    for child in list(root):
        part_name = child.get("PartName", "").lower()
        extension = child.get("Extension", "").lower()
        if "comments" in part_name or part_name.endswith("/word/people.xml") or extension == "svg":
            root.remove(child)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def archive_existing(output: Path) -> Path | None:
    if not output.exists():
        return None
    archived = output.with_name(f"{output.stem}-old{output.suffix}")
    index = 2
    while archived.exists():
        archived = output.with_name(f"{output.stem}-old-{index}{output.suffix}")
        index += 1
    output.replace(archived)
    return archived


def png_dimensions(path: Path) -> tuple[int, int]:
    payload = path.read_bytes()
    if payload[:8] != b"\x89PNG\r\n\x1a\n" or payload[12:16] != b"IHDR":
        raise ValueError(f"diagram is not a supported PNG: {path}")
    return struct.unpack(">II", payload[16:24])


def fitted_extent(path: Path, max_cx: int, max_cy: int) -> tuple[str, str]:
    width, height = png_dimensions(path)
    scale = min(max_cx / width, max_cy / height)
    return str(round(width * scale)), str(round(height * scale))


def create_docx(template: Path, output: Path, data: dict, diagrams: Path) -> Path | None:
    package = data["package_name"]
    framework_path = diagrams / f"{package}-framework.png"
    flow_path = diagrams / f"{package}-flow.png"
    framework_extent = fitted_extent(framework_path, 5_600_000, 3_600_000)
    flow_extent = fitted_extent(flow_path, 4_800_000, 6_000_000)
    with zipfile.ZipFile(template) as source:
        members = {name: source.read(name) for name in source.namelist()}
    members["word/document.xml"] = build_document(
        members["word/document.xml"], data, framework_extent, flow_extent
    )
    members["word/_rels/document.xml.rels"] = strip_relationships(members["word/_rels/document.xml.rels"])
    members["[Content_Types].xml"] = strip_content_types(members["[Content_Types].xml"])
    members["word/media/image1.png"] = framework_path.read_bytes()
    members["word/media/image2.png"] = flow_path.read_bytes()
    for name in list(members):
        lowered = name.lower()
        if "comments" in lowered or lowered.endswith("word/people.xml") or lowered.endswith(".svg"):
            del members[name]

    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=output.stem + "-", suffix=".docx", dir=output.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for name, payload in members.items():
                target.writestr(name, payload)
        archived = archive_existing(output)
        os.replace(temp, output)
        return archived
    finally:
        if temp.exists():
            temp.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--diagrams", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    for data_path in sorted(args.data_dir.glob("algo1-4-j-*.json"), key=lambda p: int(p.stem.rsplit("-", 1)[1])):
        data = json.loads(data_path.read_text(encoding="utf-8"))
        output = args.output_dir / f"{data['package_name']}模型原理说明.docx"
        archived = create_docx(args.template, output, data, args.diagrams)
        if archived:
            print(f"archived: {archived}")
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generate model-principle DOCX files from the approved commented template."""

from __future__ import annotations

import argparse
import json
import os
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


def build_table(sample: ET.Element, data: dict) -> ET.Element:
    rows = sample.findall(W + "tr")
    metadata_sample = next(row for row in rows if len(row.findall(W + "tc")) == 2)
    detail_sample = next(row for row in rows if len(row.findall(W + "tc")) == 3)
    result = deepcopy(sample)
    for row in list(result.findall(W + "tr")):
        result.remove(row)

    metadata = [
        ("课题名称", data.get("project_name", "自主式交通系统跨域计算与决策优化")),
        ("专题名称", data.get("topic_name", "端边云协同的多方式自主交通系统全域认知计算")),
        ("模型编号", data["algorithm_id"]),
        ("模型名称", data["algorithm_name"]),
        ("模型功能描述", data["function_description"]),
        ("输入数据要求", data["input_summary"]),
    ]
    for label, value in metadata:
        result.append(table_row(metadata_sample, [label, value]))
    for item in data["inputs"]:
        result.append(table_row(detail_sample, ["", item["name"], item["detail"]]))
    result.append(table_row(metadata_sample, ["输出数据要求", data["output_summary"]]))
    for item in data["outputs"]:
        result.append(table_row(detail_sample, ["", item["name"], item["detail"]]))
    for label, value in (
        ("模型服务场景", data["service_scene"]),
        ("上游接口模型编号", data["upstream_model_id"]),
        ("下游接口模型编号", data["downstream_model_id"]),
        ("交付时间", data["delivery_time"]),
        ("责任单位", data["responsible_unit"]),
    ):
        result.append(table_row(metadata_sample, [label, value]))
    return result


def resize_drawing(paragraph: ET.Element, cx: str, cy: str) -> ET.Element:
    result = deepcopy(paragraph)
    for extent in result.iter(WP + "extent"):
        extent.set("cx", cx)
        extent.set("cy", cy)
    return result


def build_document(template_xml: bytes, data: dict) -> bytes:
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
    body.append(resize_drawing(framework_drawing, "5600000", "2426667"))
    body.append(clone_paragraph(caption_sample, "算法框架图"))
    body.append(clone_paragraph(h1_flow, "3 算法模型流程图"))
    body.append(resize_drawing(flow_drawing, "4800000", "5546667"))
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
        if "comments" in relation_type or relation_type.endswith("/people"):
            root.remove(child)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def strip_content_types(payload: bytes) -> bytes:
    register_namespaces(payload)
    root = ET.fromstring(payload)
    for child in list(root):
        part_name = child.get("PartName", "").lower()
        if "comments" in part_name or part_name.endswith("/word/people.xml"):
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


def create_docx(template: Path, output: Path, data: dict, diagrams: Path) -> Path | None:
    package = data["package_name"]
    with zipfile.ZipFile(template) as source:
        members = {name: source.read(name) for name in source.namelist()}
    members["word/document.xml"] = build_document(members["word/document.xml"], data)
    members["word/_rels/document.xml.rels"] = strip_relationships(members["word/_rels/document.xml.rels"])
    members["[Content_Types].xml"] = strip_content_types(members["[Content_Types].xml"])
    members["word/media/image1.png"] = (diagrams / f"{package}-framework.png").read_bytes()
    members["word/media/image2.png"] = (diagrams / f"{package}-flow.png").read_bytes()
    members["word/media/image3.svg"] = (diagrams / f"{package}-flow.svg").read_bytes()
    for name in list(members):
        lowered = name.lower()
        if "comments" in lowered or lowered.endswith("word/people.xml"):
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

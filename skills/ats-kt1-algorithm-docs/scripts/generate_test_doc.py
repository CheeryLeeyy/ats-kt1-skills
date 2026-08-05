#!/usr/bin/env python3
"""Generate a kt_1 test-description DOCX from JSON and the approved template."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import zipfile
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
XML_NS = "http://www.w3.org/XML/1998/namespace"
W = f"{{{W_NS}}}"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"


def register_namespaces(xml_bytes: bytes) -> None:
    for _, pair in ET.iterparse(BytesIO(xml_bytes), events=("start-ns",)):
        prefix, uri = pair
        if prefix not in {"xml", "xmlns"}:
            ET.register_namespace(prefix, uri)


def paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(W + "t"))


def paragraph_style(paragraph: ET.Element) -> str:
    node = paragraph.find(f"./{W}pPr/{W}pStyle")
    return node.get(W + "val", "") if node is not None else ""


def first_run_properties(element: ET.Element) -> ET.Element | None:
    run = element.find(f".//{W}r")
    if run is None:
        return None
    props = run.find(W + "rPr")
    return deepcopy(props) if props is not None else None


def append_text(run: ET.Element, text: str) -> None:
    pieces = str(text).split("\n")
    for index, piece in enumerate(pieces):
        if index:
            ET.SubElement(run, W + "br")
        node = ET.SubElement(run, W + "t")
        if piece.startswith(" ") or piece.endswith(" "):
            node.set(f"{{{XML_NS}}}space", "preserve")
        node.text = piece


class TemplateBuilder:
    def __init__(self, document_xml: bytes):
        register_namespaces(document_xml)
        self.root = ET.fromstring(document_xml)
        self.body = self.root.find(W + "body")
        if self.body is None:
            raise ValueError("template has no w:body")
        paragraphs = [node for node in self.body if node.tag == W + "p"]
        tables = [node for node in self.body if node.tag == W + "tbl"]
        self.samples: dict[str, ET.Element] = {}
        for paragraph in paragraphs:
            style = paragraph_style(paragraph)
            text = paragraph_text(paragraph)
            if style == "a3" and "title" not in self.samples:
                self.samples["title"] = paragraph
            elif style == "1" and text and "h1" not in self.samples:
                self.samples["h1"] = paragraph
            elif style == "2" and text and "h2" not in self.samples:
                self.samples["h2"] = paragraph
            elif style == "3" and text and "h3" not in self.samples:
                self.samples["h3"] = paragraph
            elif style == "SourceCode" and "code" not in self.samples:
                self.samples["code"] = paragraph
            elif not style and text and "normal" not in self.samples:
                self.samples["normal"] = paragraph
        missing = {"title", "h1", "h2", "h3", "code", "normal"} - self.samples.keys()
        if missing or not tables:
            raise ValueError(f"template lacks required style samples: {sorted(missing)}")
        self.table_sample = tables[0]
        sample_rows = self.table_sample.findall(W + "tr")
        if len(sample_rows) < 2:
            raise ValueError("template table needs header and data rows")
        self.header_row_sample = sample_rows[0]
        self.data_row_sample = sample_rows[1]
        self.section = self.body.find(W + "sectPr")
        if self.section is None:
            raise ValueError("template has no section properties")
        for child in list(self.body):
            self.body.remove(child)

    def paragraph(self, role: str, text: str) -> ET.Element:
        sample = self.samples[role]
        result = deepcopy(sample)
        props = result.find(W + "pPr")
        for child in list(result):
            if child is not props:
                result.remove(child)
        run = ET.SubElement(result, W + "r")
        run_props = first_run_properties(sample)
        if run_props is not None:
            run.append(run_props)
        append_text(run, text)
        return result

    def filename_paragraph(self, filename: str) -> ET.Element:
        result = self.paragraph("normal", f"({filename})")
        run_props = result.find(f"./{W}r/{W}rPr")
        if run_props is None:
            run = result.find(W + "r")
            run_props = ET.Element(W + "rPr")
            if run is not None:
                run.insert(0, run_props)
        fonts = run_props.find(W + "rFonts")
        if fonts is None:
            fonts = ET.SubElement(run_props, W + "rFonts")
        for name in ("ascii", "eastAsia", "hAnsi"):
            fonts.set(W + name, "Consolas")
        return result

    def _cell_paragraph(self, sample_cell: ET.Element, text: str) -> ET.Element:
        sample_p = sample_cell.find(W + "p")
        if sample_p is None:
            return self.paragraph("normal", text)
        result = deepcopy(sample_p)
        props = result.find(W + "pPr")
        for child in list(result):
            if child is not props:
                result.remove(child)
        run = ET.SubElement(result, W + "r")
        run_props = first_run_properties(sample_p)
        if run_props is not None:
            run.append(run_props)
        append_text(run, text)
        return result

    def _row(self, values: list[str], header: bool, widths: list[int]) -> ET.Element:
        sample_row = self.header_row_sample if header else self.data_row_sample
        result = deepcopy(sample_row)
        row_props = result.find(W + "trPr")
        for child in list(result):
            if child is not row_props:
                result.remove(child)
        if row_props is None:
            row_props = ET.Element(W + "trPr")
            result.insert(0, row_props)
        marker = row_props.find(W + "tblHeader")
        cant_split = row_props.find(W + "cantSplit")
        if marker is not None:
            row_props.remove(marker)
        if cant_split is not None:
            row_props.remove(cant_split)
        # WordprocessingML requires cantSplit before tblHeader in CT_TrPr.
        ET.SubElement(row_props, W + "cantSplit")
        if header:
            ET.SubElement(row_props, W + "tblHeader")
        source_cells = sample_row.findall(W + "tc")
        source_cell = source_cells[0]
        for index, value in enumerate(values):
            cell = deepcopy(source_cell)
            cell_props = cell.find(W + "tcPr")
            for child in list(cell):
                if child is not cell_props:
                    cell.remove(child)
            if cell_props is None:
                cell_props = ET.Element(W + "tcPr")
                cell.insert(0, cell_props)
            cell_width = cell_props.find(W + "tcW")
            if cell_width is None:
                cell_width = ET.SubElement(cell_props, W + "tcW")
            cell_width.set(W + "w", str(widths[index]))
            cell_width.set(W + "type", "dxa")
            cell.append(self._cell_paragraph(source_cell, str(value)))
            result.append(cell)
        return result

    def table(self, headers: Iterable[Any], rows: Iterable[Iterable[Any]]) -> ET.Element:
        header_values = [str(value) for value in headers]
        if not header_values:
            raise ValueError("table headers may not be empty")
        normalized_rows = []
        for source in rows:
            values = [str(value) for value in source]
            if len(values) != len(header_values):
                raise ValueError(f"table row has {len(values)} cells; expected {len(header_values)}")
            normalized_rows.append(values)
        if not normalized_rows:
            normalized_rows = [["—"] + [""] * (len(header_values) - 1)]
        result = deepcopy(self.table_sample)
        table_props = result.find(W + "tblPr")
        grid = result.find(W + "tblGrid")
        for child in list(result):
            if child not in {table_props, grid}:
                result.remove(child)
        if grid is None:
            grid = ET.Element(W + "tblGrid")
            result.insert(1 if table_props is not None else 0, grid)
        for child in list(grid):
            grid.remove(child)
        width = 8311 // len(header_values)
        remainder = 8311 - width * len(header_values)
        widths = [width + (1 if i < remainder else 0) for i in range(len(header_values))]
        for col_width in widths:
            col = ET.SubElement(grid, W + "gridCol")
            col.set(W + "w", str(col_width))
        result.append(self._row(header_values, True, widths))
        for values in normalized_rows:
            result.append(self._row(values, False, widths))
        return result

    def add(self, element: ET.Element) -> None:
        self.body.append(element)

    def finish(self) -> bytes:
        self.body.append(deepcopy(self.section))
        # ElementTree drops namespace declarations that occur only in the
        # lexical value of mc:Ignorable. The template's Ignorable attribute
        # then names undeclared prefixes, which Microsoft Word reports as
        # unreadable content. The cloned w14 paragraph IDs are also duplicated
        # many times. Neither is needed for document content or formatting.
        self.root.attrib.pop(f"{{{MC_NS}}}Ignorable", None)
        for element in self.root.iter():
            for attribute in list(element.attrib):
                if attribute.startswith(f"{{{W14_NS}}}"):
                    del element.attrib[attribute]
        return ET.tostring(self.root, encoding="utf-8", xml_declaration=True)


def require_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def validate_data(data: dict[str, Any]) -> None:
    algorithm_id = require_string(data, "algorithm_id")
    package_name = require_string(data, "package_name")
    require_string(data, "algorithm_name")
    require_string(data, "image")
    if not re.fullmatch(r"1-4-J-\d+", algorithm_id):
        raise ValueError("algorithm_id must match 1-4-J-N")
    expected_package = "algo" + algorithm_id.lower()
    if package_name != expected_package:
        raise ValueError(f"package_name must be {expected_package}")
    if data["image"] != f"{package_name}:v1":
        raise ValueError(f"image must be {package_name}:v1")
    for key in ("input_files", "runtime_configs", "output_files", "results", "conclusion"):
        if not isinstance(data.get(key), list) or not data[key]:
            raise ValueError(f"{key} must be a non-empty list")
    if not isinstance(data.get("test_options"), list):
        raise ValueError("test_options must be a list")
    if not data["test_options"] and not str(data.get("test_options_limitation", "")).strip():
        raise ValueError("empty test_options requires test_options_limitation")
    for option in data["test_options"]:
        if not str(option.get("path", "")).startswith("test_options/"):
            raise ValueError("each test_options path must point to a real test_options/ input directory")
    conclusion_text = "".join(str(value) for value in data["conclusion"])
    if algorithm_id not in conclusion_text or data["algorithm_name"] not in conclusion_text:
        raise ValueError("conclusion must contain the current algorithm_id and algorithm_name")
    for phrase in ("预期", "可以判断", "测试通过"):
        if phrase not in conclusion_text:
            raise ValueError(f"conclusion must contain predictive pass-condition wording: {phrase}")
    for key in ("load_command", "linux_command", "windows_command", "run_note"):
        require_string(data, key)


def render_blocks(builder: TemplateBuilder, blocks: Any) -> None:
    if blocks is None:
        return
    if isinstance(blocks, dict):
        blocks = [blocks]
    if not isinstance(blocks, list):
        raise ValueError("content/blocks must be an object or list")
    for block in blocks:
        if not isinstance(block, dict):
            raise ValueError("each content block must be an object")
        kind = block.get("type", "text")
        if kind == "table":
            builder.add(builder.table(block.get("headers") or [], block.get("rows") or []))
        elif kind == "code":
            builder.add(builder.paragraph("code", str(block.get("text", ""))))
        elif kind == "text":
            builder.add(builder.paragraph("normal", str(block.get("text", ""))))
        else:
            raise ValueError(f"unsupported content block type: {kind}")


def build_document(template_xml: bytes, data: dict[str, Any]) -> bytes:
    builder = TemplateBuilder(template_xml)
    algorithm_id = data["algorithm_id"]
    builder.add(builder.paragraph("title", f"{algorithm_id} {data['algorithm_name']}"))
    builder.add(builder.paragraph("title", "测试说明"))

    builder.add(builder.paragraph("h1", "1 测试数据与配置"))
    builder.add(builder.paragraph("normal", "本节记录本次测试实际采用的输入数据和可替换输入样例，用于说明模型测试所依据的原始实验数据；容器运行配置统一在2.1节列出。"))
    builder.add(builder.paragraph("h2", "1.1 测试输入文件清单"))
    builder.add(
        builder.table(
            ["文件名", "格式", "是否必须", "说明"],
            [
                [item["name"], item["format"], item.get("required", "是"), item["description"]]
                for item in data["input_files"]
            ],
        )
    )

    builder.add(builder.paragraph("h2", "1.2 实际输入数据"))
    for index, item in enumerate(data["input_files"], 1):
        builder.add(builder.paragraph("h3", f"1.2.{index} {item.get('title') or item['name']}"))
        builder.add(builder.filename_paragraph(item["name"]))
        builder.add(builder.paragraph("normal", item.get("detail") or item["description"]))
        render_blocks(builder, item.get("content"))

    builder.add(builder.paragraph("h2", "1.3 可泛化样例"))
    builder.add(
        builder.paragraph(
            "normal",
            data.get("test_options_intro")
            or "除默认输入外，提交包提供以下可替换测试样例。各样例保持相同的数据组织形式，可独立挂载到容器输入目录。",
        )
    )
    if data.get("test_options_limitation"):
        builder.add(builder.paragraph("normal", str(data["test_options_limitation"])))
    if data["test_options"]:
        builder.add(
            builder.table(
                ["测试样例", "输入目录", "数据概况", "实测状态或用途"],
                [
                    [item["name"], item["path"], item["summary"], item.get("status", "可替换测试输入")]
                    for item in data["test_options"]
                ],
            )
        )
    for option in data["test_options"]:
        if option.get("description"):
            builder.add(builder.paragraph("normal", f"{option['name']}：{option['description']}"))

    builder.add(builder.paragraph("h1", "2 测试过程"))
    builder.add(builder.paragraph("normal", "本次测试通过容器方式复现算法运行过程，将输入数据目录和输出数据目录挂载到容器内，运行结束后检查退出状态、输出文件及关键结果。"))
    builder.add(builder.paragraph("h2", "2.1 Docker运行配置"))
    builder.add(
        builder.paragraph(
            "normal",
            data.get("runtime_config_intro")
            or "下列配置属于每次容器运行均需采用的运行条件，不是可泛化输入样例。",
        )
    )
    if data.get("runtime_config_source"):
        builder.add(builder.paragraph("normal", str(data["runtime_config_source"])))
    builder.add(
        builder.table(
            ["配置项", "类型", "本次值", "允许值或来源", "作用"],
            [
                [
                    item["name"],
                    item.get("type", "—"),
                    item.get("default", "—"),
                    item.get("range", "—"),
                    item["description"],
                ]
                for item in data["runtime_configs"]
            ],
        )
    )
    builder.add(builder.paragraph("h2", "2.2 Docker运行命令"))
    builder.add(builder.paragraph("code", data["load_command"]))
    builder.add(builder.paragraph("code", data["linux_command"]))
    builder.add(builder.paragraph("code", data["windows_command"]))
    builder.add(builder.paragraph("normal", data["run_note"]))
    if data.get("execution_summary"):
        builder.add(builder.paragraph("normal", data["execution_summary"]))
    builder.add(builder.paragraph("h1", "3 预期测试结果"))
    for index, item in enumerate(data["results"], 1):
        builder.add(builder.paragraph("h2", f"3.{index} {item['title']}"))
        if item.get("filename"):
            builder.add(builder.filename_paragraph(item["filename"]))
        builder.add(builder.paragraph("normal", item["description"]))
        render_blocks(builder, item.get("content"))

    builder.add(builder.paragraph("h1", "4 测试通过条件"))
    for paragraph in data["conclusion"]:
        builder.add(builder.paragraph("normal", str(paragraph)))
    return builder.finish()


def strip_relationships(xml_bytes: bytes) -> bytes:
    register_namespaces(xml_bytes)
    root = ET.fromstring(xml_bytes)
    blocked = ("comments", "people", "/image")
    for child in list(root):
        relation_type = child.get("Type", "").lower()
        if any(token in relation_type for token in blocked):
            root.remove(child)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def strip_content_types(xml_bytes: bytes) -> bytes:
    register_namespaces(xml_bytes)
    root = ET.fromstring(xml_bytes)
    for child in list(root):
        part = child.get("PartName", "").lower()
        if "comments" in part or part.endswith("/word/people.xml"):
            root.remove(child)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def create_docx(template: Path, output: Path, document_xml: bytes) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=output.stem + "-", suffix=".docx", dir=output.parent)
    os.close(fd)
    temp_path = Path(temp_name)
    blocked_parts = {
        "word/comments.xml",
        "word/commentsExtended.xml",
        "word/commentsIds.xml",
        "word/commentsExtensible.xml",
        "word/people.xml",
    }
    try:
        with zipfile.ZipFile(template, "r") as source, zipfile.ZipFile(
            temp_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as target:
            for info in source.infolist():
                name = info.filename
                if name in blocked_parts or name.startswith("word/media/"):
                    continue
                payload = source.read(name)
                if name == "word/document.xml":
                    payload = document_xml
                elif name == "word/_rels/document.xml.rels":
                    payload = strip_relationships(payload)
                elif name == "[Content_Types].xml":
                    payload = strip_content_types(payload)
                target.writestr(info, payload)
        temp_path.replace(output)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    data = json.loads(args.data.read_text(encoding="utf-8"))
    validate_data(data)
    expected_name = f"{data['package_name']}测试说明.docx"
    if args.output.name != expected_name:
        raise ValueError(f"output filename must be {expected_name}")
    with zipfile.ZipFile(args.template, "r") as archive:
        template_xml = archive.read("word/document.xml")
    document_xml = build_document(template_xml, data)
    create_docx(args.template, args.output, document_xml)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

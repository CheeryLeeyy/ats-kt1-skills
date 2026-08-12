#!/usr/bin/env python3
"""Validate naming, OOXML integrity, required content, and removed comments."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
W = f"{{{W_NS}}}"


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docx", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path)
    args = parser.parse_args()
    data = json.loads(args.data.read_text(encoding="utf-8"))
    errors: list[str] = []
    expected_name = f"{data['package_name']}测试说明.docx"
    if args.docx.name != expected_name:
        fail(errors, f"filename is {args.docx.name!r}; expected {expected_name!r}")
    try:
        with zipfile.ZipFile(args.docx, "r") as archive:
            corrupt = archive.testzip()
            if corrupt:
                fail(errors, f"corrupt ZIP member: {corrupt}")
            names = set(archive.namelist())
            for name in names:
                lowered = name.lower()
                if "comments" in lowered or lowered.endswith("word/people.xml"):
                    fail(errors, f"comment metadata remains: {name}")
            document_xml = archive.read("word/document.xml")
            for rels_name in sorted(name for name in names if name.endswith(".rels")):
                rels_root = ET.fromstring(archive.read(rels_name))
                if rels_name == "_rels/.rels":
                    base = ""
                else:
                    owner_dir = posixpath.dirname(posixpath.dirname(rels_name))
                    base = owner_dir
                for relation in rels_root.findall(f"{{{REL_NS}}}Relationship"):
                    if relation.get("TargetMode") == "External":
                        continue
                    target = relation.get("Target", "")
                    resolved = posixpath.normpath(posixpath.join(base, target))
                    if resolved not in names:
                        fail(errors, f"relationship target is missing: {rels_name} -> {resolved}")
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        fail(errors, f"cannot read DOCX: {exc}")
        document_xml = b""
    if document_xml:
        if b"Ignorable=" in document_xml:
            fail(errors, "mc:Ignorable remains; generated DOCX must not reference dropped namespace prefixes")
        root = ET.fromstring(document_xml)
        extension_attributes = [
            attribute
            for element in root.iter()
            for attribute in element.attrib
            if attribute.startswith(f"{{{W14_NS}}}")
        ]
        if extension_attributes:
            fail(errors, f"duplicated Word extension paragraph attributes remain: {len(extension_attributes)}")
        body_text = "".join(node.text or "" for node in root.iter(W + "t"))
        paragraphs = [
            "".join(node.text or "" for node in paragraph.iter(W + "t"))
            for paragraph in root.iter(W + "p")
        ]
        anchored = [
            element
            for element in root.iter()
            if element.tag
            in {
                W + "commentRangeStart",
                W + "commentRangeEnd",
                W + "commentReference",
            }
        ]
        if anchored:
            fail(errors, f"{len(anchored)} comment anchors remain in document.xml")
        required_headings = [
            "1 测试数据与配置",
            "1.1 测试输入文件清单",
            "1.2 实际输入数据",
            "1.3 可泛化样例",
            "2 测试过程",
            "2.1 Docker运行配置",
            "2.2 Docker运行命令",
            "3 预期测试结果",
            "4 测试通过条件",
        ]
        for heading in required_headings:
            if heading not in paragraphs:
                fail(errors, f"required heading missing: {heading}")
        obsolete_headings = (
            "2.1 运行方式",
            "2.1.1 运行配置",
            "2.1.2 Docker运行命令",
            "2.2 输出文件清单",
            "3 测试结果",
            "4 测试结论",
        )
        for heading in obsolete_headings:
            if heading in paragraphs:
                fail(errors, f"obsolete heading remains: {heading}")
        if all(heading in paragraphs for heading in ("1.3 可泛化样例", "2 测试过程", "2.1 Docker运行配置", "2.2 Docker运行命令", "3 预期测试结果")):
            section_13 = "\n".join(
                paragraphs[
                    paragraphs.index("1.3 可泛化样例") + 1 : paragraphs.index("2 测试过程")
                ]
            )
            section_21_config = "\n".join(
                paragraphs[
                    paragraphs.index("2.1 Docker运行配置") + 1 : paragraphs.index("2.2 Docker运行命令")
                ]
            )
            section_22 = "\n".join(
                paragraphs[
                    paragraphs.index("2.2 Docker运行命令") + 1 : paragraphs.index("3 预期测试结果")
                ]
            )
            for item in data.get("runtime_configs", []):
                name = str(item["name"])
                if name in section_13:
                    fail(errors, f"runtime configuration appears in section 1.3: {name}")
                if name not in section_21_config:
                    fail(errors, f"runtime configuration missing from section 2.1: {name}")
            source = str(data.get("runtime_config_source", "")).strip()
            if source and source not in section_21_config:
                fail(errors, "runtime_config_source is not in section 2.1")
            for item in data.get("test_options", []):
                name = str(item["name"])
                if name not in section_13:
                    fail(errors, f"test option is not in section 1.3: {name}")
            for command_key in ("load_command", "linux_command", "windows_command"):
                first_line = str(data.get(command_key, "")).splitlines()[0]
                if first_line and first_line not in section_22:
                    fail(errors, f"{command_key} is not in section 2.2")
            section_3 = "\n".join(
                paragraphs[
                    paragraphs.index("3 预期测试结果") + 1 : paragraphs.index("4 测试通过条件")
                ]
            )
            for item in data.get("output_files", []):
                if str(item["name"]) not in section_3:
                    fail(errors, f"output file is not described in section 3: {item['name']}")
        for key in ("algorithm_id", "algorithm_name", "package_name", "image"):
            value = str(data[key])
            if value not in body_text:
                fail(errors, f"required value missing from document: {key}={value}")
        other_packages = set(re.findall(r"algo1-4-j-\d+", body_text)) - {str(data["package_name"])}
        other_ids = set(re.findall(r"1-4-J-\d+", body_text)) - {str(data["algorithm_id"])}
        if other_packages:
            fail(errors, f"other algorithm package ids appear: {sorted(other_packages)}")
        if other_ids:
            fail(errors, f"other business algorithm ids appear: {sorted(other_ids)}")
        conclusion_text = "".join(str(value) for value in data.get("conclusion", []))
        if str(data.get("algorithm_id")) not in conclusion_text or str(data.get("algorithm_name")) not in conclusion_text:
            fail(errors, "structured conclusion does not contain the current algorithm id and name")
        for collection in ("input_files", "output_files"):
            for item in data.get(collection, []):
                name = str(item["name"])
                if name not in body_text:
                    fail(errors, f"listed file missing from document: {name}")
        if len(data.get("test_options", [])) < 2:
            limitation = str(data.get("test_options_limitation", "")).strip()
            if not limitation:
                fail(errors, "fewer than two test_options without test_options_limitation")
            elif limitation not in body_text:
                fail(errors, "test_options_limitation is missing from document")
        for item in data.get("test_options", []):
            if str(item["name"]) not in body_text:
                fail(errors, f"test option missing from document: {item['name']}")
            if not str(item.get("path", "")).startswith("test_options/"):
                fail(errors, f"test option is not a real test_options/ input directory: {item.get('path')}")
        residues = [
            "流量传播张量构建基础模型",
            "detector_trajectory.parquet",
            "dispersion_params.npz",
            "algo4-4-j-1:v1",
            "algo1-4-j-1.tar",
            "test_option_1_2021_08_22_13_37_16",
        ]
        structured_text = json.dumps(data, ensure_ascii=False)
        if data.get("package_name") != "algo1-4-j-1":
            for residue in residues:
                if residue in body_text and residue not in structured_text:
                    fail(errors, f"template example residue remains: {residue}")
        placeholders = [
            value
            for value in re.findall(r"\{[^{}\n]{1,80}\}", body_text)
            if value not in {"{PWD}"}
        ]
        if placeholders:
            fail(errors, f"possible placeholders remain: {placeholders[:5]}")
        table_count = sum(1 for _ in root.iter(W + "tbl"))
        if table_count < 2:
            fail(errors, f"too few tables: {table_count}; expected at least 2")
        for row_props in root.iter(W + "trPr"):
            children = list(row_props)
            cant_index = next((i for i, child in enumerate(children) if child.tag == W + "cantSplit"), None)
            header_index = next((i for i, child in enumerate(children) if child.tag == W + "tblHeader"), None)
            if cant_index is not None and header_index is not None and cant_index > header_index:
                fail(errors, "invalid CT_TrPr child order: cantSplit must precede tblHeader")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {args.docx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

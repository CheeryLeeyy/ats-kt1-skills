#!/usr/bin/env python3
"""Restore the model-introduction section from a same-algorithm legacy DOCX.

The section is copied as OOXML so native Word equations are preserved. Any
relationship-bound images used by the section are copied into the destination
package with new relationship identifiers.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import posixpath
import re
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
W14_URI = "http://schemas.microsoft.com/office/word/2010/wordml"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"
DOCUMENT_PART = "word/document.xml"
DOCUMENT_RELS = "word/_rels/document.xml.rels"


def element_text(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.iter(W + "t")).strip()


def strip_compatibility_markup(element: ET.Element) -> None:
    """Remove Word 2010-only formatting that the clean target package omits."""
    namespace_prefix = "{" + W14_URI + "}"
    for parent in element.iter():
        for attribute in list(parent.attrib):
            if attribute.startswith(namespace_prefix):
                del parent.attrib[attribute]
        for child in list(parent):
            if child.tag.startswith(namespace_prefix):
                parent.remove(child)


def serialize_document(root: ET.Element) -> bytes:
    namespaces = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "a14": "http://schemas.microsoft.com/office/drawing/2010/main",
        "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
        "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    }
    for prefix, uri in namespaces.items():
        ET.register_namespace(prefix, uri)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def serialize_default_namespace(root: ET.Element, uri: str) -> bytes:
    ET.register_namespace("", uri)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def find_section(body: ET.Element) -> tuple[int, int]:
    children = list(body)
    start = None
    for index, child in enumerate(children):
        text = element_text(child).replace(" ", "")
        if text.startswith("2算法模型简介"):
            start = index
            break
    if start is None:
        raise ValueError("未找到“2 算法模型简介”标题")

    for index in range(start + 1, len(children)):
        text = element_text(children[index]).replace(" ", "")
        if text.startswith("算法框架图") or re.match(r"^3(?:算法设计|算法模型)", text):
            return start, index
    raise ValueError("未找到第 2 章后的“算法框架图”或第 3 章标题")


def relationship_map(root: ET.Element) -> dict[str, ET.Element]:
    return {
        rel.attrib["Id"]: rel
        for rel in root.findall(PKG_REL + "Relationship")
        if "Id" in rel.attrib
    }


def next_relationship_id(root: ET.Element) -> str:
    values = []
    for rel in root.findall(PKG_REL + "Relationship"):
        match = re.fullmatch(r"rId(\d+)", rel.attrib.get("Id", ""))
        if match:
            values.append(int(match.group(1)))
    return f"rId{max(values, default=0) + 1}"


def unique_part_name(existing: set[str], source_name: str, counter: int) -> str:
    suffix = PurePosixPath(source_name).suffix
    candidate = f"word/media/restored_intro_{counter}{suffix}"
    while candidate in existing:
        counter += 1
        candidate = f"word/media/restored_intro_{counter}{suffix}"
    return candidate


def merge_content_type_default(
    source_root: ET.Element, target_root: ET.Element, extension: str
) -> None:
    extension = extension.lstrip(".").lower()
    if not extension:
        return
    for item in target_root.findall(CT + "Default"):
        if item.attrib.get("Extension", "").lower() == extension:
            return
    for item in source_root.findall(CT + "Default"):
        if item.attrib.get("Extension", "").lower() == extension:
            target_root.append(copy.deepcopy(item))
            return


def clone_section_with_relationships(
    source_zip: zipfile.ZipFile,
    target_entries: dict[str, bytes],
    source_elements: list[ET.Element],
    source_rels_root: ET.Element,
    target_rels_root: ET.Element,
    source_types_root: ET.Element,
    target_types_root: ET.Element,
) -> tuple[list[ET.Element], list[dict[str, str]]]:
    source_rels = relationship_map(source_rels_root)
    cloned = [copy.deepcopy(element) for element in source_elements]
    for element in cloned:
        strip_compatibility_markup(element)
    copied: list[dict[str, str]] = []
    existing = set(target_entries)
    rel_rewrites: dict[str, str] = {}
    part_counter = 1

    for element in cloned:
        for node in element.iter():
            for attribute, old_id in list(node.attrib.items()):
                if not attribute.startswith(R) or old_id not in source_rels:
                    continue
                if old_id in rel_rewrites:
                    node.attrib[attribute] = rel_rewrites[old_id]
                    continue

                source_rel = source_rels[old_id]
                new_id = next_relationship_id(target_rels_root)
                new_rel = copy.deepcopy(source_rel)
                new_rel.attrib["Id"] = new_id

                if source_rel.attrib.get("TargetMode") != "External":
                    source_target = source_rel.attrib.get("Target", "")
                    source_part = posixpath.normpath(
                        posixpath.join(posixpath.dirname(DOCUMENT_PART), source_target)
                    )
                    if source_part not in source_zip.namelist():
                        raise ValueError(
                            f"旧文档关系 {old_id} 指向缺失部件：{source_part}"
                        )
                    new_part = unique_part_name(existing, source_part, part_counter)
                    part_counter += 1
                    existing.add(new_part)
                    target_entries[new_part] = source_zip.read(source_part)
                    new_rel.attrib["Target"] = posixpath.relpath(
                        new_part, posixpath.dirname(DOCUMENT_PART)
                    )
                    merge_content_type_default(
                        source_types_root,
                        target_types_root,
                        PurePosixPath(source_part).suffix,
                    )
                    copied.append(
                        {
                            "source_relationship": old_id,
                            "target_relationship": new_id,
                            "source_part": source_part,
                            "target_part": new_part,
                        }
                    )
                else:
                    copied.append(
                        {
                            "source_relationship": old_id,
                            "target_relationship": new_id,
                            "external_target": source_rel.attrib.get("Target", ""),
                        }
                    )

                target_rels_root.append(new_rel)
                rel_rewrites[old_id] = new_id
                node.attrib[attribute] = new_id

    return cloned, copied


def validate_relationship_targets(entries: dict[str, bytes]) -> list[str]:
    rels_root = ET.fromstring(entries[DOCUMENT_RELS])
    missing = []
    for rel in rels_root.findall(PKG_REL + "Relationship"):
        if rel.attrib.get("TargetMode") == "External":
            continue
        target = rel.attrib.get("Target", "")
        part = posixpath.normpath(
            posixpath.join(posixpath.dirname(DOCUMENT_PART), target)
        )
        if part not in entries:
            missing.append(f"{rel.attrib.get('Id', '')}:{part}")
    return missing


def restore(source: Path, target: Path, output: Path) -> dict[str, object]:
    with zipfile.ZipFile(source) as source_zip, zipfile.ZipFile(target) as target_zip:
        source_doc = ET.fromstring(source_zip.read(DOCUMENT_PART))
        target_doc = ET.fromstring(target_zip.read(DOCUMENT_PART))
        source_body = source_doc.find(W + "body")
        target_body = target_doc.find(W + "body")
        if source_body is None or target_body is None:
            raise ValueError("DOCX 缺少 word/document.xml 的 body")

        source_start, source_end = find_section(source_body)
        target_start, target_end = find_section(target_body)
        source_elements = list(source_body)[source_start + 1 : source_end]
        if not source_elements:
            raise ValueError("旧文档第 2 章没有可恢复内容")

        source_rels = ET.fromstring(source_zip.read(DOCUMENT_RELS))
        target_rels = ET.fromstring(target_zip.read(DOCUMENT_RELS))
        source_types = ET.fromstring(source_zip.read("[Content_Types].xml"))
        target_types = ET.fromstring(target_zip.read("[Content_Types].xml"))
        entries = {name: target_zip.read(name) for name in target_zip.namelist()}

        cloned, copied = clone_section_with_relationships(
            source_zip,
            entries,
            source_elements,
            source_rels,
            target_rels,
            source_types,
            target_types,
        )

        for element in list(target_body)[target_start + 1 : target_end]:
            target_body.remove(element)
        insertion = target_start + 1
        for element in cloned:
            target_body.insert(insertion, element)
            insertion += 1

        entries[DOCUMENT_PART] = serialize_document(target_doc)
        entries[DOCUMENT_RELS] = serialize_default_namespace(
            target_rels,
            "http://schemas.openxmlformats.org/package/2006/relationships",
        )
        entries["[Content_Types].xml"] = serialize_default_namespace(
            target_types,
            "http://schemas.openxmlformats.org/package/2006/content-types",
        )

    missing = validate_relationship_targets(entries)
    if missing:
        raise ValueError("输出文档存在缺失关系目标：" + "，".join(missing))

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=output.stem + ".", suffix=".docx", dir=output.parent, delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with zipfile.ZipFile(
            temporary_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as output_zip:
            for name, data in entries.items():
                output_zip.writestr(name, data)
        os.replace(temporary_path, output)
    finally:
        temporary_path.unlink(missing_ok=True)

    formula_nodes = sum(
        1
        for element in source_elements
        for node in element.iter()
        if node.tag == M + "oMath"
    )
    paragraphs = [element_text(element) for element in source_elements]
    return {
        "source": str(source),
        "target": str(target),
        "output": str(output),
        "restored_elements": len(source_elements),
        "restored_formula_nodes": formula_nodes,
        "restored_relationships": copied,
        "restored_text": [text for text in paragraphs if text],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()

    result = restore(args.source, args.target, args.output)
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

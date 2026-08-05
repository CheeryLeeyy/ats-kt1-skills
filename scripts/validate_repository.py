#!/usr/bin/env python3
"""Validate the public ATS topic-one skills repository without external dependencies."""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/ats-kt1-algorithm-docs"
REQUIRED = (
    ROOT / "README.md",
    ROOT / ".gitignore",
    SKILL / "SKILL.md",
    SKILL / "agents/openai.yaml",
    SKILL / "assets/测试说明-示例.docx",
    SKILL / "assets/模型原理说明-示例.docx",
    SKILL / "references/算法提交说明.md",
    SKILL / "references/数据结构规范.md",
)
TEXT_SUFFIXES = {".md", ".py", ".yaml", ".yml", ".txt", ".json", ".gitignore"}
BLOCKED_PATTERNS = {
    "server home path": re.compile(r"/home/ly(?:/|\b)"),
    "server data path": re.compile(r"/mnt/disk2(?:/|\b)"),
    "GitHub classic token": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    "GitHub fine-grained token": re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
}
CP = "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}"
DC = "{http://purl.org/dc/elements/1.1/}"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def text_files() -> list[Path]:
    result = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.name == ".gitignore" or path.suffix.lower() in TEXT_SUFFIXES:
            result.append(path)
    return result


def main() -> int:
    errors: list[str] = []
    for path in REQUIRED:
        if not path.is_file():
            errors.append(f"required file missing: {path.relative_to(ROOT)}")

    skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    if not skill_text.startswith("---\nname: ats-kt1-algorithm-docs\ndescription:"):
        errors.append("SKILL.md frontmatter is invalid")
    if skill_text.find("\n---\n", 4) == -1:
        errors.append("SKILL.md frontmatter is not closed")
    if len(skill_text.splitlines()) > 500:
        errors.append("SKILL.md exceeds 500 lines")
    if "TODO" in skill_text:
        errors.append("SKILL.md contains TODO placeholders")
    for required_text in (
        "最新命名 XLSX 是可选输入",
        "从该算法文件夹内已有测试说明或模型原理说明",
        "不使用 `algo1-4-j-N` 文件夹编号冒充模型名称",
        "测试说明参考模板或示例",
        "模型原理说明参考模板或示例",
    ):
        if required_text not in skill_text:
            errors.append(f"SKILL.md is missing required workflow text: {required_text}")

    agent_text = (SKILL / "agents/openai.yaml").read_text(encoding="utf-8")
    if "$ats-kt1-algorithm-docs" not in agent_text:
        errors.append("agents/openai.yaml default_prompt does not name the skill")

    for path in text_files():
        try:
            value = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"text file is not UTF-8: {path.relative_to(ROOT)}: {exc}")
            continue
        if path.resolve() != Path(__file__).resolve():
            for label, pattern in BLOCKED_PATTERNS.items():
                if pattern.search(value):
                    errors.append(f"{label} found in {path.relative_to(ROOT)}")
        if path.suffix == ".py":
            try:
                compile(value, str(path), "exec")
            except SyntaxError as exc:
                errors.append(f"Python syntax error in {path.relative_to(ROOT)}: {exc}")

    for asset in (SKILL / "assets").glob("*.docx"):
        try:
            with zipfile.ZipFile(asset) as archive:
                corrupt = archive.testzip()
                if corrupt:
                    errors.append(f"corrupt DOCX asset member: {asset.name}: {corrupt}")
                core = ET.fromstring(archive.read("docProps/core.xml"))
                creators = [core.findtext(DC + "creator", ""), core.findtext(CP + "lastModifiedBy", "")]
                if any(value != "ATS课题一" for value in creators):
                    errors.append(f"personal core metadata remains in {asset.name}")
                if "word/comments.xml" in archive.namelist():
                    comments = ET.fromstring(archive.read("word/comments.xml"))
                    authors = {comment.get(W + "author", "") for comment in comments.iter(W + "comment")}
                    if authors != {"ATS课题一"}:
                        errors.append(f"personal comment author metadata remains in {asset.name}: {sorted(authors)}")
        except zipfile.BadZipFile:
            errors.append(f"invalid DOCX asset: {asset.name}")

    for path in ROOT.rglob("*"):
        if path.is_file() and ".git" not in path.parts and path.stat().st_size > 5 * 1024 * 1024:
            errors.append(f"file exceeds 5 MiB public-repository limit: {path.relative_to(ROOT)}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

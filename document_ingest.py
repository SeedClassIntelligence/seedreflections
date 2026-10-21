"""Exhaustive document extraction into the Seed Reflections archive contract."""

from __future__ import annotations

import csv
import html
import io
import json
import mimetypes
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

from archive_store import find_source_import, import_json, import_json_path, import_text, preserve_source, preserve_source_path


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        if data.strip():
            self.parts.append(data.strip())


def _pdf(content):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(content))
    pages = []
    unreadable = []
    for index, page in enumerate(reader.pages, 1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            pages.append(f"[Page {index}]\n{text.strip()}")
        else:
            unreadable.append(index)
    coverage = {"unit": "pages", "detected": len(reader.pages), "processed": len(reader.pages) - len(unreadable),
                "unreadable": unreadable, "status": "complete" if not unreadable else "partial"}
    return "\n\n".join(pages), coverage


def _docx(content):
    paragraphs = []
    with zipfile.ZipFile(io.BytesIO(content)) as package:
        names = [name for name in package.namelist() if name.startswith("word/") and name.endswith(".xml")]
        ordered = [name for name in ("word/document.xml", "word/footnotes.xml", "word/endnotes.xml", "word/comments.xml") if name in names]
        ordered += sorted(name for name in names if name.startswith("word/header") or name.startswith("word/footer"))
        for name in ordered:
            root = ElementTree.fromstring(package.read(name))
            text = " ".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
            if text.strip():
                paragraphs.append(f"[{Path(name).stem}]\n{text.strip()}")
    return "\n\n".join(paragraphs), {"unit": "document_parts", "detected": len(ordered), "processed": len(paragraphs),
                                             "unreadable": [], "status": "complete" if len(ordered) == len(paragraphs) else "partial"}


def _xlsx(content):
    from openpyxl import load_workbook
    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=False)
    sections = []
    for sheet in workbook.worksheets:
        rows = []
        for row in sheet.iter_rows(values_only=True):
            values = ["" if value is None else str(value) for value in row]
            if any(values):
                rows.append("\t".join(values))
        sections.append(f"[Sheet: {sheet.title}]\n" + "\n".join(rows))
    return "\n\n".join(sections), {"unit": "sheets", "detected": len(workbook.sheetnames), "processed": len(sections),
                                           "unreadable": [], "status": "complete"}


def _html(content):
    parser = _HTMLText()
    parser.feed(content.decode("utf-8", errors="replace"))
    return "\n".join(parser.parts)


def _rtf(content):
    value = content.decode("utf-8", errors="replace")
    value = re.sub(r"\\'[0-9a-fA-F]{2}", " ", value)
    value = re.sub(r"\\[a-zA-Z]+-?\d* ?", " ", value)
    value = value.replace("{", "").replace("}", "")
    return html.unescape(re.sub(r"\s+", " ", value)).strip()


def _zip(content):
    sections, failures, detected = [], [], 0
    with zipfile.ZipFile(io.BytesIO(content)) as package:
        for info in package.infolist():
            if info.is_dir() or info.file_size > 250 * 1024 * 1024:
                continue
            detected += 1
            try:
                child = extract_document(package.read(info), info.filename, allow_zip=False)
                sections.append(f"[File: {info.filename}]\n{child['text']}")
                if child["coverage"]["status"] != "complete":
                    failures.append(info.filename)
            except Exception:
                failures.append(info.filename)
    return "\n\n".join(sections), {"unit": "files", "detected": detected, "processed": detected - len(failures),
                                           "unreadable": failures, "status": "complete" if not failures else "partial"}


def extract_document(content, filename, allow_zip=True):
    extension = Path(filename).suffix.lower()
    if extension == ".pdf":
        text, coverage = _pdf(content)
    elif extension == ".docx":
        text, coverage = _docx(content)
    elif extension in {".xlsx", ".xlsm"}:
        text, coverage = _xlsx(content)
    elif extension in {".html", ".htm"}:
        text = _html(content); coverage = {"unit":"file", "detected":1, "processed":1, "unreadable":[], "status":"complete"}
    elif extension == ".rtf":
        text = _rtf(content); coverage = {"unit":"file", "detected":1, "processed":1, "unreadable":[], "status":"complete"}
    elif extension == ".zip" and allow_zip:
        text, coverage = _zip(content)
    elif extension in {".txt", ".md", ".csv", ".tsv", ".log", ".xml"}:
        text = content.decode("utf-8-sig", errors="replace")
        coverage = {"unit":"file", "detected":1, "processed":1, "unreadable":[], "status":"complete"}
    else:
        raise ValueError(f"Unsupported document type: {extension or 'unknown'}")
    if not text.strip():
        coverage["status"] = "partial"
        coverage["reason"] = "No readable text was extracted. OCR may be required."
    return {"text": text, "coverage": coverage}


def import_document(content, filename):
    existing = find_source_import(content)
    if existing:
        return {**existing, "filename": Path(filename).name}
    extension = Path(filename).suffix.lower()
    if extension == ".json":
        result = import_json(content, filename)
        coverage = {"unit":"archive", "detected":len(result["conversations"]), "processed":len(result["conversations"]),
                    "unreadable":[], "status":"complete"}
    else:
        extracted = extract_document(content, filename)
        coverage = extracted["coverage"]
        result = import_text(extracted["text"], Path(filename).stem, filename)
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    preserve_source(result["import_id"], filename, media_type, content, coverage)
    return {**result, "coverage": coverage, "filename": Path(filename).name}


def import_document_path(path, filename):
    source = Path(path)
    if source.suffix.lower() == ".json" or Path(filename).suffix.lower() == ".json":
        result = import_json_path(source, filename)
        coverage = {"unit":"archive", "detected":len(result["conversations"]), "processed":len(result["conversations"]),
                    "unreadable":[], "status":"complete"}
        preserve_source_path(result["import_id"], filename, "application/json", source, coverage)
        return {**result, "coverage":coverage, "filename":Path(filename).name}
    return import_document(source.read_bytes(), filename)

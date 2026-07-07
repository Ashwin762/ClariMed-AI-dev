"""

Reads the real, authored markdown files under /knowledge_base/disease/**/*.md
and parses them into structured docs. This replaces the old approach where
kb_initializer.py had its own hardcoded duplicate strings that ignored the
actual .md files on disk.

Each .md file is expected to have YAML frontmatter (---...---) followed by
markdown content with `#`/`##` headers, matching the template already used
in conjuctivities.md / dry_eye.md.
"""

from __future__ import annotations
import os
import re
from typing import Dict, Any, List
import yaml

KB_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "knowledge_base", "disease")


def _split_frontmatter(raw: str):
    raw = raw.replace("\r\n", "\n")
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.DOTALL)
    if not match:
        return {}, raw
    fm_text, body = match.groups()
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, body


def _split_sections(body: str) -> Dict[str, str]:
    """
    Split markdown body into {section_title: section_text} using top-level
    '# ' and '## ' headers as boundaries. Keeps things simple and robust to
    the loose structure already used in the authored files.
    """
    lines = body.split("\n")
    sections: Dict[str, List[str]] = {}
    current = "Overview"
    sections[current] = []
    for line in lines:
        h = re.match(r"^#{1,2}\s+(.*)$", line.strip())
        if h:
            title = h.group(1).strip().lstrip("🟢🟡🔴 ").strip()
            current = title
            sections.setdefault(current, [])
            continue
        sections[current].append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items() if "".join(v).strip()}


def load_doc(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    fm, body = _split_frontmatter(raw)
    sections = _split_sections(body)
    return {
        "id": fm.get("id", os.path.basename(path)),
        "disease_name": fm.get("disease_name", os.path.splitext(os.path.basename(path))[0]),
        "aliases": fm.get("aliases", []) or [],
        "body_part": (fm.get("body_part") or "").strip().lower(),
        "specialist": fm.get("specialist", ""),
        "emergency_possible": bool(fm.get("emergency_possible", False)),
        "keywords": [str(k).strip().lower() for k in (fm.get("keywords") or [])],
        "version": fm.get("version", "1.0"),
        "sections": sections,
        "full_text": body,
        "source_path": path,
    }


def load_all_docs(kb_root: str = None) -> List[Dict[str, Any]]:
    root = kb_root or KB_ROOT
    docs = []
    if not os.path.isdir(root):
        return docs
    for dirpath, _, filenames in os.walk(root):
        for fn in sorted(filenames):
            if fn.endswith(".md"):
                try:
                    docs.append(load_doc(os.path.join(dirpath, fn)))
                except Exception as e:
                    print(f"[kb_loader] Failed to parse {fn}: {e}")
    return docs


def get_section(doc: Dict[str, Any], *candidates: str, default: str = "") -> str:
    """Fetch a section by trying several possible header spellings."""
    for c in candidates:
        for key, text in doc["sections"].items():
            if key.strip().lower() == c.strip().lower():
                return text
    return default


if __name__ == "__main__":
    docs = load_all_docs()
    print(f"Loaded {len(docs)} knowledge base document(s):")
    for d in docs:
        print(f"  - {d['id']} :: {d['disease_name']} ({d['body_part']}) keywords={d['keywords'][:4]}...")
        print(f"      sections found: {list(d['sections'].keys())[:6]} ...")
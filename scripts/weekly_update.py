#!/usr/bin/env python3
"""EconBoard weekly updater: discover candidates and merge reviewed entries."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data.js"
CONFIG_FILE = ROOT / "config" / "sources.json"
APPROVED_FILE = ROOT / "config" / "approved_entries.json"
CANDIDATES_FILE = ROOT / "review" / "candidates.json"
REPORT_FILE = ROOT / "review" / "weekly-report.md"
PREFIX = "window.ECONBOARD_DATA = "
USER_AGENT = "EconBoard-Weekly-Updater/1.0"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_site_data() -> dict[str, Any]:
    raw = DATA_FILE.read_text(encoding="utf-8").strip()
    if not raw.startswith(PREFIX) or not raw.endswith(";"):
        raise ValueError("data.js 格式异常：应为 window.ECONBOARD_DATA = {...};")
    return json.loads(raw[len(PREFIX):-1])


def save_site_data(data: dict[str, Any]) -> None:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    DATA_FILE.write_text(f"{PREFIX}{payload};\n", encoding="utf-8")


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read()


def clean_title(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    return re.sub(r"\s+-\s+[^-]{2,30}$", "", value).strip()


def stable_id(title: str) -> str:
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:12]
    return f"candidate-{digest}"


def google_news_url(query: str) -> str:
    params = urllib.parse.urlencode({"q": query, "hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"})
    return f"https://news.google.com/rss/search?{params}"


def parse_feed(xml_bytes: bytes, query: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_bytes)
    items: list[dict[str, Any]] = []
    for node in root.findall(".//item"):
        title = clean_title(node.findtext("title", ""))
        link = (node.findtext("link", "") or "").strip()
        source_node = node.find("source")
        source = (source_node.text or "").strip() if source_node is not None else ""
        source_url = source_node.attrib.get("url", "") if source_node is not None else ""
        published = (node.findtext("pubDate", "") or "").strip()
        if title and link:
            items.append({
                "id": stable_id(title),
                "title": title,
                "sourceName": source,
                "sourceHome": source_url,
                "discoveryUrl": link,
                "publishedAt": published,
                "query": query,
            })
    return items


def score_candidate(item: dict[str, Any], config: dict[str, Any]) -> tuple[int, list[str]]:
    text = f"{item['title']} {item.get('sourceName', '')}".lower()
    score = 0
    reasons: list[str] = []
    for keyword in config["positive_keywords"]:
        if keyword.lower() in text:
            score += 2
            reasons.append(f"包含有效关键词：{keyword}")
    for keyword in config["negative_keywords"]:
        if keyword.lower() in text:
            score -= 8
            reasons.append(f"命中排除关键词：{keyword}")
    if str(datetime.now().year) in text:
        score += 2
        reasons.append("标题包含当前年份")
    source_home = item.get("sourceHome", "").lower()
    if any(domain in source_home for domain in config["trusted_domains"]):
        score += 3
        reasons.append("来源域名在可信清单中")
    return score, reasons


def discover(config: dict[str, Any], existing_titles: set[str]) -> tuple[list[dict[str, Any]], list[str]]:
    found: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for query in config["queries"]:
        try:
            for item in parse_feed(fetch(google_news_url(query)), query):
                if item["title"] in existing_titles:
                    continue
                score, reasons = score_candidate(item, config)
                if score <= 0:
                    continue
                item["score"] = score
                item["reasons"] = reasons
                item["reviewStatus"] = "待人工核验"
                old = found.get(item["id"])
                if old is None or score > old["score"]:
                    found[item["id"]] = item
        except Exception as exc:  # keep other feeds running
            errors.append(f"{query}: {exc}")
    candidates = sorted(found.values(), key=lambda item: (-item["score"], item["title"]))
    return candidates[: int(config.get("max_candidates", 40))], errors


def validate_entry(entry: dict[str, Any]) -> None:
    required = ["id", "type", "title", "organizer", "officialUrl", "sourceName", "sourceUrl"]
    missing = [key for key in required if not entry.get(key)]
    if missing:
        raise ValueError(f"已审核条目 {entry.get('id', '<unknown>')} 缺字段：{', '.join(missing)}")
    if entry["type"] not in {"competition", "forum"}:
        raise ValueError(f"条目 {entry['id']} 的 type 必须为 competition 或 forum")
    for key in ("registerEnd", "eventStart", "eventEnd"):
        value = entry.get(key)
        if value and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError(f"条目 {entry['id']} 的 {key} 日期格式应为 YYYY-MM-DD")


def merge_approved(data: dict[str, Any], approved: dict[str, Any]) -> tuple[int, int]:
    entries = data.setdefault("entries", [])
    positions = {entry["id"]: index for index, entry in enumerate(entries)}
    added = updated = 0
    for entry in approved.get("entries", []):
        validate_entry(entry)
        entry = dict(entry)
        entry.setdefault("updatedAt", datetime.now().date().isoformat())
        if entry["id"] in positions:
            entries[positions[entry["id"]]] = entry
            updated += 1
        else:
            positions[entry["id"]] = len(entries)
            entries.append(entry)
            added += 1
    data["updatedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data["sourceCount"] = len(entries)
    data.setdefault("errors", [])
    return added, updated


def write_review(candidates: list[dict[str, Any]], errors: list[str], added: int, updated: int) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    CANDIDATES_FILE.parent.mkdir(parents=True, exist_ok=True)
    CANDIDATES_FILE.write_text(json.dumps({"generatedAt": now, "candidates": candidates}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# EconBoard 自动周更报告",
        "",
        f"- 执行时间（UTC）：{now}",
        f"- 新增已审核条目：{added}",
        f"- 更新已审核条目：{updated}",
        f"- 待核验候选：{len(candidates)}",
        "",
        "## 待人工核验候选",
        "",
    ]
    if candidates:
        for item in candidates:
            reasons = "；".join(item["reasons"])
            lines.append(f"- [{item['title']}]({item['discoveryUrl']})｜来源：{item['sourceName'] or '未知'}｜评分：{item['score']}｜{reasons}")
    else:
        lines.append("本周没有发现达到初筛阈值的新候选。")
    if errors:
        lines.extend(["", "## 抓取错误", ""] + [f"- {error}" for error in errors])
    lines.extend(["", "> 候选不会自动发布。核验官方页面、截止日期、投稿通道和本科生资格后，将完整条目加入 config/approved_entries.json。"])
    REPORT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="仅检查本地数据，不联网抓取")
    args = parser.parse_args()
    try:
        config = load_json(CONFIG_FILE)
        approved = load_json(APPROVED_FILE)
        data = load_site_data()
        added, updated = merge_approved(data, approved)
        existing_titles = {entry.get("title", "") for entry in data["entries"]}
        candidates, errors = ([], []) if args.check else discover(config, existing_titles)
        save_site_data(data)
        write_review(candidates, errors, added, updated)
        print(f"OK entries={len(data['entries'])} added={added} updated={updated} candidates={len(candidates)}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

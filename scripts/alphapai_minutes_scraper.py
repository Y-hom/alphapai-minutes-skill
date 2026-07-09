#!/usr/bin/env python3
"""
Collect AlphaPai meeting minutes by keyword and save them as Obsidian Markdown.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests


BASE_URL = "https://alphapai-web.rabyte.cn"
LIST_API = f"{BASE_URL}/external/alpha/api/reading/roadshow/summary/list"
DETAIL_API = f"{BASE_URL}/external/alpha/api/reading/roadshow/summary/detail"
DETAIL_URL = f"{BASE_URL}/reading/home/meeting/detail?articleId={{id}}"
SUCCESS_CODE = 200000
DES_IV = b"\x01\x02\x03\x04\x05\x06\x07\x08"


class AlphaPaiError(RuntimeError):
    pass


@dataclass
class AuthConfig:
    authorization: str = ""
    secret_key: str = ""


def load_auth(path: Optional[str]) -> AuthConfig:
    auth = AuthConfig(
        authorization=os.environ.get("ALPHAPAI_AUTHORIZATION", "").strip(),
        secret_key=os.environ.get("ALPHAPAI_SECRET_KEY", "").strip(),
    )
    if path:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        data = data.get("alphapai", data)
        auth.authorization = (data.get("authorization") or data.get("USER_AUTH_TOKEN") or auth.authorization).strip()
        auth.secret_key = (data.get("secret_key") or data.get("SECRET_KEY") or data.get("sk") or auth.secret_key).strip()
    return auth


def sanitize_filename(text: str, fallback: str = "alphapai-note") -> str:
    text = re.sub(r"[\\/:*?\"<>|\r\n\t]+", " ", text or "").strip()
    text = re.sub(r"\s+", " ", text)
    text = text[:90].strip(" .")
    return text or fallback


def strip_html(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def yaml_string(value: Any) -> str:
    text = "" if value is None else str(value)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def compact_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def decrypt_des_cbc_base64(cipher_text: str, secret_key: str) -> Any:
    try:
        from Crypto.Cipher import DES
        from Crypto.Util.Padding import unpad
    except ImportError as exc:
        raise AlphaPaiError("Encrypted response received. Install pycryptodome to decrypt it: pip install pycryptodome") from exc

    key = secret_key.encode("utf-8")[:8]
    if len(key) != 8:
        raise AlphaPaiError("SECRET_KEY must provide at least 8 bytes for DES decryption.")
    raw = base64.b64decode(cipher_text)
    plain = unpad(DES.new(key, DES.MODE_CBC, DES_IV).decrypt(raw), DES.block_size)
    return json.loads(plain.decode("utf-8"))


class AlphaPaiClient:
    def __init__(self, auth: AuthConfig, timeout: int = 30, verbose: bool = False) -> None:
        self.auth = auth
        self.timeout = timeout
        self.verbose = verbose
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/reading/home/my-focus",
                "User-Agent": "Mozilla/5.0 AlphaPaiRawCollector/1.0",
                "x-from": "web",
            }
        )
        if auth.authorization:
            self.session.headers["Authorization"] = auth.authorization
        if auth.secret_key:
            self.session.cookies.set("sk", auth.secret_key, domain="alphapai-web.rabyte.cn")

    def _update_secret_from_headers(self, response: requests.Response) -> None:
        header = response.headers.get("x-access-sk") or response.headers.get("X-Access-Sk") or ""
        match = re.search(r"sk=([^;]+)", header)
        if match:
            self.auth.secret_key = match.group(1)
            self.session.cookies.set("sk", self.auth.secret_key, domain="alphapai-web.rabyte.cn")

    def _decode_response(self, response: requests.Response) -> Dict[str, Any]:
        self._update_secret_from_headers(response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise AlphaPaiError(f"Non-JSON response from AlphaPai: HTTP {response.status_code}") from exc

        if isinstance(payload.get("data"), str) and self.auth.secret_key:
            payload["data"] = decrypt_des_cbc_base64(payload["data"], self.auth.secret_key)

        code = payload.get("code")
        if str(code) not in {str(SUCCESS_CODE), "200000.0"}:
            msg = payload.get("msg") or payload.get("message") or "unknown error"
            if str(code) in {"401000", "401"}:
                raise AlphaPaiError("AlphaPai authentication failed: check Authorization and SECRET_KEY.")
            raise AlphaPaiError(f"AlphaPai API error {code}: {msg}")
        return payload

    def post_json(self, url: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if self.verbose:
            print(f"POST {url} {data}", file=sys.stderr)
        response = self.session.post(url, json=data, timeout=self.timeout)
        return self._decode_response(response)

    def get_json(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if self.verbose:
            print(f"GET {url} {params}", file=sys.stderr)
        response = self.session.get(url, params=params, timeout=self.timeout)
        return self._decode_response(response)


def pick_id(item: Dict[str, Any]) -> str:
    for key in ("id", "articleId", "bizId", "summaryId"):
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def extract_items_from_flow(data: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], int]:
    records: List[Dict[str, Any]] = []
    total = 0

    if isinstance(data, dict) and isinstance(data.get("list"), list):
        total = int(data.get("total") or len(data.get("list") or []))
        return [item for item in data.get("list") or [] if isinstance(item, dict)], total

    flow = data.get("informationFlow") if isinstance(data, dict) else None
    if isinstance(flow, dict):
        total = int(flow.get("total") or 0)
        for wrapper in flow.get("list") or []:
            item_type = wrapper.get("type")
            item = wrapper.get("roadshowSummary") or wrapper.get("summary") or wrapper.get("meeting") or {}
            if item_type == 31 and isinstance(item, dict):
                item = dict(item)
                item["_flow_type"] = item_type
                records.append(item)

    roadshow = data.get("roadshowSummary") if isinstance(data, dict) else None
    if isinstance(roadshow, dict):
        total = max(total, int(roadshow.get("total") or 0))
        for item in roadshow.get("list") or []:
            if isinstance(item, dict):
                records.append(item)

    return records, total


def search_minutes(
    client: AlphaPaiClient,
    query: str,
    pages: int,
    size: int,
    delay: float,
    max_items: Optional[int],
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for page in range(1, pages + 1):
        body = {
            "pageNum": page,
            "pageSize": size,
            "word": query,
        }
        payload = client.post_json(LIST_API, body)
        items, total = extract_items_from_flow(payload.get("data") or {})
        if not items:
            break
        for item in items:
            item_id = pick_id(item)
            key = item_id or json.dumps(item, ensure_ascii=False, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            results.append(item)
            if max_items and len(results) >= max_items:
                return results
        if total and len(results) >= total:
            break
        time.sleep(delay)
    return results


def get_detail(client: AlphaPaiClient, item_id: str) -> Optional[Dict[str, Any]]:
    if not item_id:
        return None
    payload = client.get_json(DETAIL_API, {"id": item_id})
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def first_value(data: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, "", []):
            return value
    return ""


def parse_datetime(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 1_000_000_000_000:
            timestamp = timestamp / 1000
        try:
            return datetime.fromtimestamp(timestamp)
        except (OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return parse_datetime(int(text))
    text = text.replace("/", "-").replace("T", " ")
    text = re.sub(r"\.\d+", "", text)
    text = re.sub(r"(Z|[+-]\d{2}:?\d{2})$", "", text).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S %Z"):
        try:
            return datetime.strptime(text[: len(fmt)], fmt)
        except ValueError:
            continue
    match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if match:
        return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return None


def item_datetime(item: Dict[str, Any], detail: Optional[Dict[str, Any]] = None) -> Optional[datetime]:
    keys = (
        "roadshowDate",
        "meetingDate",
        "publishTime",
        "createdAt",
        "createdTime",
        "updateTime",
        "date",
        "time",
    )
    for data in (detail or {}, item):
        value = first_value(data, keys)
        parsed = parse_datetime(value)
        if parsed:
            return parsed
    return None


def filter_recent_items(
    items: List[Dict[str, Any]],
    details: Dict[str, Optional[Dict[str, Any]]],
    days: Optional[int],
) -> List[Dict[str, Any]]:
    if not days:
        return items
    cutoff = datetime.now() - timedelta(days=days)
    recent: List[Dict[str, Any]] = []
    for item in items:
        dt = item_datetime(item, details.get(pick_id(item)))
        if dt and dt >= cutoff:
            recent.append(item)
    return recent


def names(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    out = []
    for item in values:
        if isinstance(item, dict):
            value = item.get("name") or item.get("stockName") or item.get("label") or item.get("code")
            if value:
                out.append(str(value))
        elif item:
            out.append(str(item))
    return out


def content_from_detail(data: Dict[str, Any]) -> str:
    sections: List[str] = []

    for key in ("summary", "content", "htmlContent", "aiSummary", "mtSummary", "abstract", "text"):
        value = data.get(key)
        if isinstance(value, str) and strip_html(value):
            sections.append(strip_html(value))

    for key in ("robotSummary", "convertSummary"):
        value = data.get(key)
        if isinstance(value, dict):
            sections.append(content_from_detail(value))

    for key in ("content", "summaryContent", "paragraphs", "aiContent"):
        value = data.get(key)
        if isinstance(value, list):
            sections.append(paragraphs_to_text(value))

    cleaned = [section for section in sections if section.strip()]
    return "\n\n".join(cleaned)


def paragraphs_to_text(value: Any) -> str:
    if isinstance(value, str):
        return strip_html(value)
    if isinstance(value, dict):
        role = value.get("role") or value.get("speaker") or ""
        children = value.get("children")
        if children:
            text = paragraphs_to_text(children)
        else:
            text = strip_html(first_value(value, ("content", "text", "p", "paragraph")))
        return f"{role}: {text}".strip(": ").strip()
    if isinstance(value, list):
        parts = [paragraphs_to_text(item) for item in value]
        return "\n\n".join(part for part in parts if part)
    return ""


def build_markdown(query: str, item: Dict[str, Any], detail: Optional[Dict[str, Any]], partial_reason: str = "") -> str:
    data = detail or item
    item_id = pick_id(data) or pick_id(item)
    title = strip_html(first_value(data, ("title", "articleTitle", "name"))) or strip_html(first_value(item, ("title", "articleTitle", "name"))) or query
    date = first_value(data, ("roadshowDate", "date", "publishTime", "createdAt", "createdTime")) or first_value(item, ("roadshowDate", "date", "publishTime", "createdAt", "createdTime"))
    stock_names = names(data.get("stock") or item.get("stock"))
    industry_names = names(data.get("industry") or item.get("industry") or data.get("sector") or item.get("sector"))
    source_url = DETAIL_URL.format(id=item_id) if item_id else BASE_URL
    scraped_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    content = content_from_detail(data) or strip_html(first_value(item, ("summary", "content", "desc", "description", "abstract", "text")))

    frontmatter = [
        "---",
        f"title: {yaml_string(title)}",
        'source: "Alpha派"',
        'source_type: "Alpha派会议纪要"',
        f"query: {yaml_string(query)}",
        f"alpha_id: {yaml_string(item_id)}",
        f"source_url: {yaml_string(source_url)}",
        f"meeting_date: {yaml_string(date)}",
        f"scraped_at: {yaml_string(scraped_at)}",
        "tags: [raw, Alpha派, 会议纪要]",
        "---",
        "",
    ]

    body = [
        f"# {title}",
        "",
        "## Source",
        "",
        f"- Query: {query}",
        f"- AlphaPai ID: {item_id or 'unknown'}",
        f"- URL: {source_url}",
        f"- Date: {date or 'unknown'}",
        f"- Stocks: {', '.join(stock_names) if stock_names else 'unknown'}",
        f"- Industries: {', '.join(industry_names) if industry_names else 'unknown'}",
    ]
    if partial_reason:
        body.append(f"- Capture status: partial ({partial_reason})")
    body.extend(["", "## Content", "", content or "_No readable content extracted. See raw JSON below._", "", "## Raw JSON", "", "```json", compact_json({"list_item": item, "detail": detail}), "```", ""])
    return "\n".join(frontmatter + body)


def write_notes(query: str, items: List[Dict[str, Any]], details: Dict[str, Optional[Dict[str, Any]]], output_dir: Path) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    for index, item in enumerate(items, 1):
        item_id = pick_id(item)
        detail = details.get(item_id)
        title_source = detail or item
        title = strip_html(first_value(title_source, ("title", "articleTitle", "name"))) or f"{query}-{index}"
        date = str(first_value(title_source, ("roadshowDate", "date", "publishTime", "createdAt", "createdTime")) or "")[:10]
        prefix = date if re.match(r"\d{4}-\d{2}-\d{2}", date) else datetime.now().strftime("%Y-%m-%d")
        filename = sanitize_filename(f"{prefix} Alpha派 {title} {item_id}") + ".md"
        path = output_dir / filename
        suffix = 1
        while path.exists():
            path = output_dir / (sanitize_filename(f"{prefix} Alpha派 {title} {item_id}-{suffix}") + ".md")
            suffix += 1
        partial = "" if detail else "detail unavailable or skipped"
        path.write_text(build_markdown(query, item, detail, partial), encoding="utf-8")
        written.append(path)
    return written


def resolve_output_dir(args: argparse.Namespace) -> Path:
    if args.output:
        return Path(args.output)
    if args.vault:
        return Path(args.vault) / "Raw_Sources" / "Alpha派会议纪要"
    return Path("Raw_Sources") / "Alpha派会议纪要"


def main() -> int:
    parser = argparse.ArgumentParser(description="Search AlphaPai meeting minutes and save Obsidian raw Markdown notes.")
    parser.add_argument("query", help="Topic, company name, stock name, or keyword to search.")
    parser.add_argument("--vault", help="Obsidian vault root. Output goes to Raw_Sources/Alpha派会议纪要.")
    parser.add_argument("-o", "--output", help="Output directory for Markdown files.")
    parser.add_argument("--auth-file", help="JSON file containing alphapai.authorization and alphapai.secret_key.")
    parser.add_argument("--pages", type=int, default=5, help="Maximum list pages to request. Default: 5.")
    parser.add_argument("--size", type=int, default=15, help="Page size. Default: 15.")
    parser.add_argument("--max-items", type=int, help="Maximum notes to write.")
    parser.add_argument("--days", type=int, help="Only write meeting minutes dated within the last N days.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between list pages in seconds. Default: 1.0.")
    parser.add_argument("--no-detail", action="store_true", help="Skip detail API and save list-card data only.")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds. Default: 30.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print request diagnostics.")
    args = parser.parse_args()

    auth = load_auth(args.auth_file)
    if not auth.authorization:
        raise AlphaPaiError("Missing Authorization. Set ALPHAPAI_AUTHORIZATION or use --auth-file.")

    client = AlphaPaiClient(auth, timeout=args.timeout, verbose=args.verbose)
    items = search_minutes(client, args.query, args.pages, args.size, args.delay, args.max_items)
    if not items:
        print("No matching AlphaPai meeting minutes found.")
        return 0

    details: Dict[str, Optional[Dict[str, Any]]] = {}
    items = filter_recent_items(items, details, args.days)
    if not items:
        print(f"No AlphaPai meeting minutes found within the last {args.days} days.")
        return 0

    if not args.no_detail:
        for item in items:
            item_id = pick_id(item)
            try:
                details[item_id] = get_detail(client, item_id)
            except Exception as exc:
                if args.verbose:
                    print(f"Detail failed for {item_id}: {exc}", file=sys.stderr)
                details[item_id] = None
            time.sleep(args.delay)

    items = filter_recent_items(items, details, args.days)
    if not items:
        print(f"No AlphaPai meeting minutes found within the last {args.days} days.")
        return 0

    output_dir = resolve_output_dir(args)
    files = write_notes(args.query, items, details, output_dir)
    print(f"Wrote {len(files)} AlphaPai meeting-minute notes to {output_dir}")
    for path in files:
        print(path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AlphaPaiError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2)

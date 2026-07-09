#!/usr/bin/env python3
"""Collect AlphaPai meeting minutes through a persistent Edge browser profile."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import sync_playwright

from alphapai_minutes_scraper import (
    BASE_URL,
    DETAIL_API,
    LIST_API,
    AlphaPaiError,
    compact_json,
    decrypt_des_cbc_base64,
    extract_items_from_flow,
    filter_recent_items,
    pick_id,
    write_notes,
)


SUCCESS_CODE = 200000


def launch_context(pw: Any, profile: Path, headless: bool) -> Any:
    profile.mkdir(parents=True, exist_ok=True)
    options = {
        "user_data_dir": str(profile),
        "headless": headless,
        "viewport": {"width": 1360, "height": 900},
        "locale": "zh-CN",
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    errors: List[str] = []
    for channel in ("msedge", "chrome", None):
        try:
            if channel:
                return pw.chromium.launch_persistent_context(channel=channel, **options)
            return pw.chromium.launch_persistent_context(**options)
        except Exception as exc:
            errors.append(f"{channel or 'playwright-chromium'}: {exc}")
    raise RuntimeError("Could not launch Edge/Chrome/Chromium:\n" + "\n".join(errors))


def login(profile: Path) -> None:
    with sync_playwright() as pw:
        context = launch_context(pw, profile, headless=False)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(f"{BASE_URL}/reading/home/my-focus", wait_until="domcontentloaded", timeout=60_000)
        print("A browser window is open.")
        print("Log in to AlphaPai in Edge/Chrome, confirm the my-focus page works, then press Enter here.")
        input()
        context.close()


def browser_state(page: Any) -> Dict[str, str]:
    return page.evaluate(
        """() => ({
            authorization:
                localStorage.getItem('USER_AUTH_TOKEN') ||
                localStorage.getItem('Authorization') ||
                localStorage.getItem('authorization') ||
                '',
            secretKey:
                localStorage.getItem('SECRET_KEY') ||
                localStorage.getItem('sk') ||
                ''
        })"""
    )


def fetch_json(page: Any, url: str, method: str = "GET", body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    state = browser_state(page)
    result = page.evaluate(
        """async ({url, method, body, authorization}) => {
            const headers = {
                'Accept': 'application/json, text/plain, */*',
                'Content-Type': 'application/json',
                'x-from': 'web'
            };
            if (authorization) headers['Authorization'] = authorization;
            const res = await fetch(url, {
                method,
                credentials: 'include',
                headers,
                body: body ? JSON.stringify(body) : undefined
            });
            return {
                status: res.status,
                contentType: res.headers.get('content-type') || '',
                accessSk: res.headers.get('x-access-sk') || '',
                text: await res.text()
            };
        }""",
        {
            "url": url,
            "method": method,
            "body": body,
            "authorization": state.get("authorization") or "",
        },
    )

    try:
        payload = json.loads(result.get("text") or "")
    except json.JSONDecodeError as exc:
        snippet = (result.get("text") or "")[:300].replace("\n", " ")
        raise AlphaPaiError(
            f"Non-JSON response from AlphaPai browser fetch. HTTP {result.get('status')}, "
            f"Content-Type={result.get('contentType') or 'unknown'}, snippet={snippet}"
        ) from exc

    secret_key = state.get("secretKey") or ""
    if isinstance(payload.get("data"), str) and secret_key:
        payload["data"] = decrypt_des_cbc_base64(payload["data"], secret_key)

    code = payload.get("code")
    if str(code) not in {str(SUCCESS_CODE), "200000.0"}:
        msg = payload.get("msg") or payload.get("message") or compact_json(payload)[:300]
        raise AlphaPaiError(f"AlphaPai API error {code}: {msg}")
    return payload


def search_minutes_browser(
    page: Any,
    query: str,
    pages: int,
    size: int,
    delay: float,
    max_items: Optional[int],
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for page_num in range(1, pages + 1):
        body = {
            "pageNum": page_num,
            "pageSize": size,
            "word": query,
        }
        print(f"Searching AlphaPai page {page_num}/{pages}: {query}")
        payload = fetch_json(page, LIST_API, method="POST", body=body)
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


def get_detail_browser(page: Any, item_id: str) -> Optional[Dict[str, Any]]:
    if not item_id:
        return None
    separator = "&" if "?" in DETAIL_API else "?"
    payload = fetch_json(page, f"{DETAIL_API}{separator}id={item_id}", method="GET")
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def resolve_output_dir(args: argparse.Namespace) -> Path:
    if args.output:
        return Path(args.output)
    if args.vault:
        return Path(args.vault) / "Raw_Sources" / "Alpha派会议纪要"
    return Path("Raw_Sources") / "Alpha派会议纪要"


def main() -> int:
    parser = argparse.ArgumentParser(description="Search AlphaPai meeting minutes through a persistent browser profile.")
    parser.add_argument("query", nargs="?", help="Topic, company name, stock name, or keyword to search.")
    parser.add_argument("--profile", default=".local/alphapai-edge-profile", help="Persistent browser profile directory.")
    parser.add_argument("--login", action="store_true", help="Open Edge/Chrome and let the user log in, then exit.")
    parser.add_argument("--vault", help="Obsidian vault root. Output goes to Raw_Sources/Alpha派会议纪要.")
    parser.add_argument("-o", "--output", help="Output directory for Markdown files.")
    parser.add_argument("--pages", type=int, default=5, help="Maximum list pages to request. Default: 5.")
    parser.add_argument("--size", type=int, default=15, help="Page size. Default: 15.")
    parser.add_argument("--max-items", type=int, help="Maximum notes to write.")
    parser.add_argument("--days", type=int, help="Only write meeting minutes dated within the last N days.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests in seconds. Default: 1.0.")
    parser.add_argument("--no-detail", action="store_true", help="Skip detail API and save list-card data only.")
    parser.add_argument("--headless", action="store_true", help="Run browser without visible window after login is done.")
    args = parser.parse_args()

    profile = Path(args.profile)
    if args.login:
        login(profile)
        print(f"Saved AlphaPai browser session in {profile}")
        return 0
    if not args.query:
        parser.error("query is required unless --login is used.")

    with sync_playwright() as pw:
        context = launch_context(pw, profile, headless=args.headless)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(f"{BASE_URL}/reading/home/my-focus", wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(2000)
            items = search_minutes_browser(page, args.query, args.pages, args.size, args.delay, args.max_items)
            if not items:
                print("No matching AlphaPai meeting minutes found.")
                return 0

            details: Dict[str, Optional[Dict[str, Any]]] = {}
            if not args.no_detail:
                for index, item in enumerate(items, 1):
                    item_id = pick_id(item)
                    try:
                        print(f"Fetching detail {index}/{len(items)}: {item_id}")
                        details[item_id] = get_detail_browser(page, item_id)
                    except Exception as exc:
                        print(f"Detail failed for {item_id}: {exc}")
                        details[item_id] = None
                    time.sleep(args.delay)
        finally:
            context.close()

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
        print(f"Error: {exc}")
        raise SystemExit(2)

---
name: alphapai-minutes-skill
description: Collect AlphaPai meeting minutes into an Obsidian vault. Use when the user asks to search AlphaPai/Alpha派 by topic, company name, stock name, or keyword and save matching meeting minutes, roadshow summaries, or 调研纪要 as raw Markdown notes. Supports a persistent Edge browser login profile by default, plus auth-file fallback.
---

# AlphaPai Meeting Minutes

Search AlphaPai by keyword and write matching meeting minutes into an Obsidian raw-source folder. Prefer the persistent browser workflow because it avoids exposing `Authorization` or `SECRET_KEY` in config files.

## Recommended: Persistent Edge Browser Profile

First-time login:

```bash
python scripts/alphapai_browser_scraper.py --login --profile .local/alphapai-edge-profile
```

The script opens Edge first, then Chrome if Edge is unavailable. Log in to AlphaPai in that browser window, confirm the `my-focus` page works, then press Enter in the terminal.

Collect meeting minutes:

```bash
python scripts/alphapai_browser_scraper.py "AI" --days 3 --vault "D:/path/to/obsidian-vault" --profile .local/alphapai-edge-profile
```

Use a plain output directory:

```bash
python scripts/alphapai_browser_scraper.py "宁德时代" --pages 3 --size 15 --max-items 20 --profile .local/alphapai-edge-profile -o "D:/path/to/vault/Raw_Sources/Alpha派会议纪要"
```

Default output:

```text
<vault>/Raw_Sources/Alpha派会议纪要
```

## Fallback: Auth File Workflow

Use this only when a browser profile is inconvenient:

```bash
python scripts/alphapai_minutes_scraper.py "AI" --days 3 --vault "D:/path/to/obsidian-vault" --auth-file config/alphapai_auth.json
```

JSON format:

```json
{
  "alphapai": {
    "authorization": "Bearer YOUR_TOKEN_HERE",
    "secret_key": "YOUR_SECRET_KEY_HERE"
  }
}
```

Environment variables:

```bash
ALPHAPAI_AUTHORIZATION=Bearer YOUR_TOKEN_HERE
ALPHAPAI_SECRET_KEY=YOUR_SECRET_KEY_HERE
```

## Capability Boundaries

- AlphaPai is authenticated. Results depend on the user’s account permissions and subscribed data scope.
- The browser workflow reuses the user’s own local Edge/Chrome session. Do not describe this as bypassing access controls.
- Detail pages may fail even when list results work; save partial notes when detail permissions are unavailable.
- Response payloads may be encrypted; the scripts try to use the browser/session secret key or auth-file secret key when needed.
- `--days` filters by parsed meeting/publish/create dates. Items without parseable dates are excluded when a day filter is used.

## Privacy And Publishing Safety

Never commit real AlphaPai login material:

- Do not commit `config/alphapai_auth.json`.
- Do not commit `.local/`, browser profiles, Playwright storage state, cookies, HAR files, or debug JSON containing headers.
- Commit only `config/alphapai_auth.json.template`.
- Keep examples filled with placeholders only.

Suggested `.gitignore` entries:

```gitignore
.env
config/alphapai_auth.json
.local/
browser-profile/
storage-state.json
*.har
debug_*.json
debug_*.png
```

## Workflow

1. Open `https://alphapai-web.rabyte.cn/reading/home/my-focus` in the persistent browser profile.
2. Reuse the browser session to request `POST /external/alpha/api/reading/information/flow/stock/information/list2`.
3. Force `type=31` to collect meeting minutes/纪要.
4. Use `word=<user topic/company>` and paginate with `pageNum/pageSize`.
5. Fetch detail from `GET /external/alpha/api/reading/summary/detail?id=<id>` when possible.
6. Filter by `--days` if requested.
7. Write one Markdown file per result with YAML frontmatter, source URL, extracted content, and raw JSON.

## Output Contract

Each Markdown note should preserve traceability:

```markdown
---
title: "会议纪要标题"
source: "Alpha派"
source_type: "Alpha派会议纪要"
query: "AI"
alpha_id: "..."
source_url: "https://alphapai-web.rabyte.cn/reading/home/meeting/detail?articleId=..."
meeting_date: "..."
scraped_at: "2026-07-09T..."
tags: [raw, Alpha派, 会议纪要]
---
```

Keep the raw JSON section unless the user explicitly asks for cleaner notes; raw notes are meant to be auditable in an Obsidian wiki pipeline.

## Common Failures

- **Not logged in**: run `alphapai_browser_scraper.py --login` and log in inside the opened Edge window.
- **Authentication failed**: the browser profile session expired; rerun `--login`.
- **Encrypted response cannot decode**: the browser profile did not expose a usable secret key; use auth-file fallback if needed.
- **No recent notes with `--days`**: matching notes may exist but have older or unparseable dates.
- **Detail unavailable**: account lacks permission for the detail page; keep partial list-card notes when useful.

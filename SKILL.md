---
name: alphapai-minutes-skill
description: Collect AlphaPai meeting minutes into an Obsidian vault. Use when the user asks to search AlphaPai/Alpha派 by topic, company name, stock name, or keyword and save matching meeting minutes, roadshow summaries, or 调研纪要 as raw Markdown notes. Requires the user’s own AlphaPai authenticated session values.
---

# AlphaPai Meeting Minutes

Search AlphaPai by keyword and write matching meeting minutes into an Obsidian raw-source folder. Prefer the bundled script because AlphaPai uses authenticated APIs, pagination, optional encrypted response payloads, and detail pages.

## Quick Start

```bash
python scripts/alphapai_minutes_scraper.py "AI" --days 3 --vault "D:/path/to/obsidian-vault" --auth-file config/alphapai_auth.json
```

Default output:

```text
<vault>/Raw_Sources/Alpha派会议纪要
```

Use a plain output directory instead of a vault:

```bash
python scripts/alphapai_minutes_scraper.py "宁德时代" -o "D:/path/to/vault/Raw_Sources/Alpha派会议纪要"
```

Limit scope:

```bash
python scripts/alphapai_minutes_scraper.py "贵州茅台" --pages 3 --size 15 --max-items 20 --days 7
```

## Capability Boundaries

- AlphaPai is authenticated. The script cannot run without the user’s own valid session values.
- Search results depend on the user’s AlphaPai account permissions and subscribed data scope.
- Detail pages may fail even when list results work; save partial notes when detail permissions are unavailable.
- Response payloads may be encrypted and require `SECRET_KEY`/`sk` plus `pycryptodome`.
- `--days` filters by parsed meeting/publish/create dates. Items without parseable dates are excluded when a day filter is used.

## Authentication

AlphaPai requires a logged-in web session. Load credentials from a JSON file or environment variables.

JSON format:

```json
{
  "alphapai": {
    "authorization": "Bearer YOUR_TOKEN_HERE",
    "secret_key": "YOUR_SECRET_KEY_HERE"
  }
}
```

A template is available at `config/alphapai_auth.json.template`. Keep the real file local and ignored by Git.

Environment variables:

```bash
ALPHAPAI_AUTHORIZATION=Bearer YOUR_TOKEN_HERE
ALPHAPAI_SECRET_KEY=YOUR_SECRET_KEY_HERE
```

How to get values:

1. Log in at `https://alphapai-web.rabyte.cn/reading/home/my-focus`.
2. Open browser developer tools.
3. Inspect authenticated requests or browser storage.
4. Copy the request `Authorization` value and the `sk`/`SECRET_KEY` value used by the web app.
5. Put them in the local auth file or environment variables.

Do not paste these tokens into notes, commits, issue reports, README files, or final answers.

## Privacy And Publishing Safety

Never commit real AlphaPai login material:

- Do not commit `config/alphapai_auth.json`.
- Do not commit `.env`, cookies, browser profiles, Playwright storage state, HAR files, or debug JSON containing headers.
- Commit only `config/alphapai_auth.json.template`.
- Keep `.gitignore` strict before publishing the repository.

Suggested `.gitignore` entries:

```gitignore
.env
config/alphapai_auth.json
cookies.json
browser-profile/
storage-state.json
*.har
debug_*.json
debug_*.png
```

## Workflow

1. Search `POST /external/alpha/api/reading/information/flow/stock/information/list2`.
2. Force `type=31` to collect meeting minutes/纪要.
3. Use `word=<user topic/company>` and paginate with `pageNum/pageSize`.
4. For each result, fetch detail from `GET /external/alpha/api/reading/summary/detail?id=<id>`.
5. Filter by `--days` if requested.
6. Write one Markdown file per result with YAML frontmatter, source URL, extracted content, and raw JSON.
7. If the detail endpoint is blocked by permissions, still save list-card data and mark the note as partial.

## API Notes

Known request headers:

```text
Authorization: <USER_AUTH_TOKEN>
x-from: web
Cookie: sk=<SECRET_KEY>
```

AlphaPai may return an updated `x-access-sk` response header. The script keeps it in memory and uses it for later requests. If a response payload is encrypted, the script tries DES-CBC decryption with IV bytes `01 02 03 04 05 06 07 08`; install `pycryptodome` if encrypted payloads need decoding.

Known type mapping:

```text
31  roadshowSummary  纪要
35  comment          点评
321 report           研报
36  announcement     公告
322 wechatArticleIndustry  产业资讯
```

This skill focuses on `31`.

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
scraped_at: "2026-07-08T..."
tags: [raw, Alpha派, 会议纪要]
---
```

Keep the raw JSON section unless the user explicitly asks for cleaner notes; raw notes are meant to be auditable in an Obsidian wiki pipeline.

## Common Failures

- **Missing Authorization**: provide `ALPHAPAI_AUTHORIZATION` or `--auth-file`.
- **Authentication failed**: token expired or copied from the wrong account/session.
- **Encrypted response cannot decode**: provide `SECRET_KEY`/`sk` and install `pycryptodome`.
- **No recent notes with `--days`**: matching notes may exist but have older or unparseable dates.
- **Detail unavailable**: account lacks permission for the detail page; keep partial list-card notes when useful.

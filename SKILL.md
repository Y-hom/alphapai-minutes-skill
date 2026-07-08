---
name: alphapai-minutes-skill
description: Collect AlphaPai meeting minutes into an Obsidian vault. Use when the user asks to search Alpha派/AlphaPai by topic, company name, stock name, or keyword and save matching meeting minutes, roadshow summaries, or 调研纪要 as raw Markdown notes for an Obsidian/wiki workflow.
---

# AlphaPai Meeting Minutes

Search AlphaPai by keyword and write matching meeting minutes into an Obsidian raw-source folder. Prefer the bundled script because AlphaPai uses authenticated APIs, pagination, optional encrypted response payloads, and detail pages.

## Quick Start

Run from this skill folder or pass the script path explicitly:

```bash
python scripts/alphapai_minutes_scraper.py "宁德时代" --vault "D:/1国海金工实习/obsidian知识库" --auth-file config/alphapai_auth.json
```

Default output:

```text
<vault>/Raw_Sources/Alpha派会议纪要/
```

Use a plain output directory instead of a vault:

```bash
python scripts/alphapai_minutes_scraper.py "固态电池" -o "D:/1国海金工实习/obsidian知识库/Raw_Sources/Alpha派会议纪要"
```

Limit scope:

```bash
python scripts/alphapai_minutes_scraper.py "贵州茅台" --pages 3 --size 15 --max-items 20
```

## Authentication

AlphaPai requires a logged-in web session. Load credentials from a JSON file or environment variables.

JSON format:

```json
{
  "alphapai": {
    "authorization": "value of localStorage.USER_AUTH_TOKEN",
    "secret_key": "value of localStorage.SECRET_KEY"
  }
}
```

A template is available at `config/alphapai_auth.json.template`.

Environment variables:

```bash
ALPHAPAI_AUTHORIZATION=...
ALPHAPAI_SECRET_KEY=...
```

How to get values:

1. Log in at `https://alphapai-web.rabyte.cn/reading/home/my-focus`.
2. Open browser developer tools.
3. In Application/Storage, copy `localStorage.USER_AUTH_TOKEN` and `localStorage.SECRET_KEY`.
4. Put them in the auth file or environment variables.

Do not paste these tokens into notes, commits, or final answers.

## Workflow

1. Search `POST /external/alpha/api/reading/information/flow/stock/information/list2`.
2. Force `type=31` to collect meeting minutes/纪要.
3. Use `word=<user topic/company>` and paginate with `pageNum/pageSize`.
4. For each result, fetch detail from `GET /external/alpha/api/reading/summary/detail?id=<id>`.
5. Write one Markdown file per result with YAML frontmatter, source URL, extracted content, and raw JSON.
6. If the detail endpoint is blocked by permissions, still save the list-card data and mark the note as partial.

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
title: "..."
source: "Alpha派"
source_type: "Alpha派会议纪要"
query: "宁德时代"
alpha_id: "..."
source_url: "https://alphapai-web.rabyte.cn/reading/home/meeting/detail?articleId=..."
scraped_at: "2026-07-08T..."
tags: [raw, Alpha派, 会议纪要]
---
```

Keep the raw JSON section unless the user explicitly asks for cleaner notes; raw notes are meant to be auditable in an Obsidian wiki pipeline.

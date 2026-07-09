# AlphaPai Minutes Skill

Collect AlphaPai meeting minutes into an Obsidian raw-source workflow.

The recommended workflow uses a persistent Edge browser profile: the user logs in locally once, and later runs reuse that local browser session. This avoids putting `Authorization`, `SECRET_KEY`, cookies, or browser storage into the repository.

## Recommended: Persistent Edge Profile

### 1. Log In Once

```powershell
cd D:\雪球爬虫skill\alphapai-minutes-skill
python scripts\alphapai_browser_scraper.py --login --profile .local\alphapai-edge-profile
```

An Edge window opens. Log in to AlphaPai, confirm the `my-focus` page works, then return to the terminal and press `Enter`.

The browser session is saved locally:

```text
.local/alphapai-edge-profile
```

This directory is ignored by Git.

### 2. Collect Meeting Minutes

Write to an Obsidian vault:

```powershell
python scripts\alphapai_browser_scraper.py "AI" --days 3 --vault D:\path\to\obsidian-vault --profile .local\alphapai-edge-profile
```

Write to a specific output directory:

```powershell
python scripts\alphapai_browser_scraper.py "宁德时代" --pages 3 --size 15 --max-items 20 --profile .local\alphapai-edge-profile -o D:\path\to\Raw_Sources\Alpha派会议纪要
```

Default vault output:

```text
<vault>/Raw_Sources/Alpha派会议纪要
```

## Fallback: Auth File

If a browser profile is inconvenient, use a local ignored auth file:

```powershell
python scripts\alphapai_minutes_scraper.py "AI" --days 3 --vault D:\path\to\obsidian-vault --auth-file config\alphapai_auth.json
```

Template:

```json
{
  "alphapai": {
    "authorization": "Bearer YOUR_TOKEN_HERE",
    "secret_key": "YOUR_SECRET_KEY_HERE"
  }
}
```

Never commit the real `config/alphapai_auth.json`.

## Privacy And GitHub Safety

Never commit:

```gitignore
config/alphapai_auth.json
.local/
browser-profile/
storage-state.json
*.har
debug_*
.env
```

Commit only templates and scripts. Real login state belongs on the user's machine.

## Common Failures

- **Not logged in**: run `alphapai_browser_scraper.py --login`.
- **Session expired**: rerun the login command.
- **No recent notes with `--days`**: matching notes may exist but be older or have unparseable dates.
- **Detail unavailable**: the account may not have permission for that meeting detail.

## Demo Script

For a screen recording:

1. Show this README and `SKILL.md`.
2. Run the `--login` command.
3. Log in inside Edge.
4. Run a query such as `AI`.
5. Open generated Markdown notes under `Raw_Sources/Alpha派会议纪要`.

Suggested narration:

> The skill uses a persistent Edge profile. Users log in locally once, and the script reuses that session to collect traceable raw meeting-minute notes into Obsidian. Login tokens never enter GitHub.

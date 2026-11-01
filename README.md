# Asset Library

A skill for turning the posts you save — and never reopen — into a library an AI can read, search, and learn from.

Built for people who save 3,000 things on 小红书 / 抖音 / B站 / X and then never look at them again, and who make things with AI and need it to know what "good" looks like.

## Why this exists

An AI only does good work when it knows what good looks like. Your saves are already that definition — you made thousands of small judgments about what was worth keeping. They are just sitting in four different apps, unreadable by anything.

This turns them into plain text on your disk: one markdown file per post, metadata and body and, where it matters, the spoken script. Any model that can read a file can use it.

## What it does

- **Collects** what you save on 抖音, 小红书, B站 and X.
- **Filters** against your own keywords, so a 3,000-item collection becomes a short list of things that are actually about your work.
- **Transcribes** the videos, because the method is usually spoken and the caption is just a hook.
- **Buckets** everything into 4–6 topics of your choosing, sorted by engagement, linking back to the original.
- **Digests** it each morning and says what each item actually taught — the trick, the number, the method — not what topic it covered.

## Install

```bash
git clone <this repo> ~/asset-library-src
mkdir -p ~/asset-lib
cp ~/asset-library-src/skills/asset-library/scripts/lib.py ~/asset-lib/
cp -r ~/asset-library-src/skills/asset-library/scripts/tools ~/asset-lib/
cp ~/asset-library-src/skills/asset-library/references/topics.example.json ~/asset-lib/topics.json
```

Then edit `topics.json` — it is the only file that matters and the only one only you can write.

For Claude Code, Codex or Cursor, copy `skills/asset-library` into your skills directory so the agent knows the workflow:

```bash
cp -r ~/asset-library-src/skills/asset-library ~/.claude/skills/
```

## Quick start

```bash
cd ~/asset-lib
# drop your scraper's output in raw/
python3 lib.py classify raw/xiaohongshu-2026-11-01.json
python3 lib.py ingest xiaohongshu raw/xiaohongshu-2026-11-01.filtered.json
python3 lib.py report
python3 lib.py topics
python3 lib.py digest
```

Or just ask your agent: *"Use asset-library. Collect what I saved today and tell me what each one actually taught."*

## How each platform works

| platform | collect | transcribe |
| --- | --- | --- |
| B站 | favourites page HTML, or `x/player/pagelist` | `tools/asr_bili.py`, no browser needed |
| 抖音 | list page in a logged-in browser | signed link captured while playing → `fetch_media.py` |
| 小红书 | list page in a logged-in browser | same as 抖音 |
| X | the X API, bookmarks and likes paginate | usually captioned already |

The 抖音 / 小红书 path is the fragile one and the skill documents the one order that works: capture the signed link while the video plays, download it immediately, transcribe afterwards. The link dies in minutes; the transcription takes hours.

## Transcription cost

Measured on 8 vCPUs with `medium` / `int8` / CPU, about **8× realtime**:

| input | wall clock |
| --- | --- |
| 1 hour of video | ~7 min |
| 100 videos × 10 min | ~2 h |
| 40-hour course | ~5 h |

It is off by default. The skill asks, with these numbers, before spending hours of your machine's time.

## Privacy

The library is personal — it is the record of what you chose to read and what those people said. The scripts hold no account data; `items/`, `index/`, `transcripts/`, `media/` and `raw/` hold all of it, and `.gitignore` keeps them out of your repo.

Collecting is read-only on every platform: never like, save, follow, comment, or change a setting.

## License

MIT.

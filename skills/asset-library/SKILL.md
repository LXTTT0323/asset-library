---
name: asset-library
description: Build and run a personal library of the posts you save on 抖音, 小红书, B站 and X — filtered by your own topics, searchable by any AI, with video transcripts and a daily digest that says what each item actually taught. Use when someone wants their saved/bookmarked content organized, searchable, or turned into a daily reading digest.
---

# Asset library

Turn "I saved 3,000 posts and never opened them again" into something an AI can actually read.

The premise: **an AI only does good work when it knows what good looks like.** What you chose to save is that definition. It is already sitting in your bookmarks — nobody ever read it. This skill reads it, keeps what matters, and hands it back in a form any model can use.

Works with Claude Code, Codex, Cursor, or any agent that can read files and run Python.

---

## What you get

```
asset-lib/
  topics.json              # your filter words + topic buckets — the only file you hand-write
  lib.py                   # one CLI: classify, ingest, report, topics, digest, stats, prune
  tools/asr_bili.py        #  B站 video -> text, no browser needed
  tools/fetch_media.py     #  signed media URL -> audio, while it is still alive
  tools/asr_media.py       #  audio -> text
  items/<platform>/        # one markdown file per saved post: metadata, body, transcript
  index/items.jsonl        # the full index, for any AI to grep
  reports/by-topic-full.md # every item, grouped by topic, sorted by likes, linking back
  reports/digest-pack-*.md # the morning reading pack
  transcripts/  media/  raw/
```

Everything is plain text. Any AI that can `cat` a file can use this library.

---

## Setup

**1. Copy the scripts somewhere.**

```bash
git clone <this repo> ~/asset-library-src
mkdir -p ~/asset-lib
cp ~/asset-library-src/skills/asset-library/scripts/lib.py ~/asset-lib/
cp -r ~/asset-library-src/skills/asset-library/scripts/tools ~/asset-lib/
```

Nothing else needs editing. There are no account ids, folder ids or profile URLs anywhere in the code, because *where* you save things is your own business and it belongs in your notes, not in a shared script.

**2. Write `topics.json`.** This is the part only you can do, and it decides whether the library is useful or noise. See [Topics](#topics) below.

**3. Get your saved list out of each platform.** This is the only manual step and it is where most people stop. See [Collecting](#collecting).

**4. Run it daily.** One cron line, or let your agent do it.

### Dependencies

Everything except transcription is Python stdlib only.

```bash
python3 -m venv .venv && .venv/bin/pip install faster-whisper numpy
# transcription also needs curl and ffmpeg
```

The first transcription downloads the whisper model (~1.5 GB for `medium`) into `~/.cache/huggingface`; after that it is cached.

---

## Topics

`topics.json` is your taste written down. Four lists:

```json
{
  "include":  ["ai", "大模型", "vibe coding", "独立开发", "剪视频"],
  "exclude":  ["带货", "抽奖", "招聘"],
  "strong":   ["claude", "cursor", "agent"],
  "buckets": [
    {"key": "tools",   "label": "AI 工具与编程", "priority": 5, "keywords": ["cursor", "claude", "codex", "skill"]},
    {"key": "money",   "label": "创业与变现",     "priority": 3, "keywords": ["变现", "独立开发", "出海"]},
    {"key": "growth",  "label": "认知与成长",     "priority": 0, "keywords": ["方法论", "复盘", "思维"]}
  ]
}
```

- **include** — an item must hit one of these to enter the library.
- **exclude** — dropped even if it hits an include word, *unless* it also hits a **strong** word. That is the whole point of `strong`: it lets "AI 招聘" get dropped while "AI agent 教程" survives.
- **buckets** — 4–6 topic groups for the report. Scored on the title first, body only when the title hits nothing. Ties go to the lower `priority` number.

Write these from what the person actually makes. A list of generic AI keywords produces a generic library.

---

## Collecting

Three different situations, three different methods. Read this before writing any scraper.

### B站 — the easy one

Your favourites page is `https://space.bilibili.com/<mid>/favlist?fid=<fid>&ftype=create`. The list HTML gives you title, author, and counts without opening anything. Video pages answer 412 to datacenter IPs, but the player APIs do not — `tools/asr_bili.py` relies on exactly that:

```bash
python3 tools/asr_bili.py --max-dur 1200 --cap 1800 --workers 2
```

`x/player/pagelist` gives the cid, `x/player/playurl` gives a signed audio stream. Resumable: rerun and finished videos are skipped.

`--max-dur 1200` skips anything longer than 20 minutes — a two-hour course or a 90-minute interview costs hours of machine time for material you will not reread, while the 10-minute posts are where the concrete tricks live. Skipped ids go into `raw/bili-long.json` and are not re-checked. Set it to `0` to transcribe everything.

### 抖音 / 小红书 — the hard one

There is no media URL in the HTML. A signed link appears **only while the video is playing in a logged-in browser**, and it dies within minutes. So the order matters and there is no way around it:

1. The browser opens the video, watches the network tab, and appends `{"platform","id","url"}` to `raw/media-queue.jsonl` — 抖音: the `media-audio` track, not `media-video`. 小红书: the single combined mp4.
2. `python3 tools/fetch_media.py --queue` downloads **immediately** into `media/<platform>-<id>.pcm` (16k mono — the video is thrown away, only audio is kept).
3. `python3 tools/asr_media.py` transcribes later, at your leisure.

Download first, transcribe after. Never interleave them: the link expires long before the transcription finishes.

If a domestic platform returns 412 or a 风控 page, that is a session or IP problem, not a code problem. Do not retry in a loop.

### X — use the API

X has a real API for this. `bookmarks` and `likes` both paginate; read to the end of the cursor. No browser, no signed links, no scraping.

### Rules that keep this from being a mess

- **Read-only, always.** Never like, save, follow, comment, or change a setting while collecting. The library is a copy of a decision the person already made.
- **Never invent a number.** If the page said `9.8万`, store that string in `count_raw`. Both `topics` and `digest` parse `万` / `w` / `k` for sorting while printing the original, so the count stays honestly approximate.
- **Filter before you open.** List page → `classify` → open only the survivors. This is what keeps a 3,000-item collection down to a dozen page loads.
- **One platform name per site, forever.** A stray `xhs` next to `xiaohongshu` splits the dedupe table and re-ingests everything.

---

## Transcription — offer it as a choice, with the cost

This is the expensive half, and the half that makes the library worth having: **the method is usually spoken, not captioned.** Ask before turning it on, and give real numbers instead of a vague "it takes a while".

Measured with `medium` / `int8` / CPU, 4 threads per worker, 2 workers on an 8-vCPU box:

| what | wall clock |
| --- | --- |
| 1 hour of video | ~7 minutes |
| 10 short videos (~30 min of audio) | ~4 minutes |
| 100 videos × 10 min (~17 h of audio) | ~2 hours |
| a 40-hour course playlist | ~5 hours |

`small` runs about twice as fast and garbles Chinese names and technical terms noticeably more.

Three honest options:

1. **Off.** Searchable by title, author and engagement. The digest can say what a post is about but not what it argues.
2. **New items only, from today.** Each morning's digest covers new videos in full; the back catalogue stays caption-only. The sane default.
3. **Backfill everything, then keep up.** Run once in the background, capped, finish overnight.

Ask for a length limit too. Course playlists can be 40 hours each, so `--cap 1800` keeps the first 30 minutes of whatever you do transcribe, and `--max-dur 1200` skips the long ones entirely.

Every finished transcript is also appended to its item's markdown, so an interrupted run still leaves the finished ones readable.

---

## Commands

```bash
cd ~/asset-lib

python3 lib.py classify raw/<platform>-<date>.json      # -> raw/…filtered.json
python3 lib.py ingest <platform> raw/…filtered.json     # always feed it the .filtered.json
python3 lib.py report                                   # reports/snapshot.md
python3 lib.py topics                                   # by-topic.md, by-topic-full.md, topics/<key>.md
python3 lib.py attach <platform> <id> <textfile>        # add a `## 口播文字稿` section
python3 lib.py digest [YYYY-MM-DD]                      # reports/digest-pack-<date>.md
python3 lib.py stats                                    # transcript coverage per platform
python3 lib.py prune [--apply]                          # drop items that no longer match topics.json
```

The library root is `$ASSET_LIB`, else the directory holding `lib.py`. `index/seen.json` stores library-relative paths, so the whole folder can be moved or renamed without breaking it.

### Item JSON (what your scraper hands to `classify` and `ingest`)

```json
{"items":[{"id","title","author","url","text","likes","collects","comments",
           "plays","published_at","cover","count_raw","kind"}]}
```

- `id` is the platform's own id (aweme id / note id / BV id).
- `kind` is `video` or `image-text`.
- Omit fields the page did not show. `ingest` keeps every non-empty field except `text`, which lives in the item's markdown.

---

## The daily digest

The point of the whole thing. Each morning: collect what is new, `classify`, `ingest`, `report`, `topics`, transcribe the day's new videos, then `lib.py digest` builds a reading pack with transcript heads and tails. Write the digest **from that pack**, and make it say what each item actually taught — the method, the number, the trick — not what topic it was about. "讲了提示词技巧" is worthless. "他说把系统提示词拆成三段，第三段只放反例，能把幻觉降下来" is the library earning its keep.

```cron
0 8 * * * cd ~/asset-lib && ./daily.sh
```

---

## Privacy

The library is personal. It holds what you chose to read and the transcript of what those people said. Keep `items/`, `index/`, `transcripts/`, `media/` and `raw/` out of any public repo — `.gitignore` in this one already does. The scripts contain no account data; the data folder contains all of it.

## License

MIT. Take it, change it, ship it.

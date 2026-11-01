#!/usr/bin/env python3
"""Transcribe every bilibili video in the library that has no transcript yet.

Bilibili's HTML pages answer 412 to datacentre IPs, but these two API endpoints
stay open: pagelist (gives the cid per page) and playurl (gives signed audio
URLs). So bilibili needs no browser at all — download the audio stream with
curl and feed it to faster-whisper.

Usage:
  python3 tools/asr_bili.py [--max-dur 1200] [--cap 1800] [--limit N] [--workers 2]

  --max-dur skip any video whose full length exceeds this many seconds
            (1200 = 20 minutes; 0 means no limit). The skipped BV ids are
            recorded in raw/bili-long.json so later runs do not re-check them.
  --cap     seconds of each video to transcribe, counted from the start
            (long course playlists would otherwise add days of audio)
  --limit   stop after N videos (for a quick trial)
  --workers parallel whisper processes; 2 is about right for 8 vCPUs

Skips anything already in index/transcripts.json. Writes
transcripts/bilibili-<bvid>.txt and attaches it to the item markdown, so
every finished video is readable even if the run is interrupted.
Progress goes to logs/asr-bili.log; rerun the same command to continue.
"""
import functools, json, os, subprocess, sys, tempfile, time, urllib.request

ROOT = os.environ.get("ASSET_LIB") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/156.0.0.0 Safari/537.36")
REF = "https://www.bilibili.com/"
API = "https://api.bilibili.com/x/player/"
PY = os.environ.get("WHISPER_PY") or sys.executable


def api(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": REF})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def pages_of(bvid):
    d = api(f"{API}pagelist?bvid={bvid}")
    return (d.get("data") or [])


def audio_url(bvid, cid):
    """Best audio-only stream for one page, or None."""
    d = api(f"{API}playurl?bvid={bvid}&cid={cid}&fnval=16&qn=80")
    data = d.get("data") or {}
    dash = data.get("dash") or {}
    audio = dash.get("audio") or []
    if audio:
        # ids: 30216 low, 30232 mid, 30280 high; pick the highest bitrate
        best = max(audio, key=lambda a: a.get("bandwidth") or 0)
        return best["baseUrl"]
    durl = data.get("durl") or []
    if durl:
        return durl[0].get("url")
    return None


def total_duration(bvid):
    """Full length of the video in seconds, summed over its parts."""
    return sum((p.get("duration") or 0) for p in pages_of(bvid))


LONG = os.path.join(ROOT, "raw", "bili-long.json")


def long_seen():
    return set(json.load(open(LONG))) if os.path.exists(LONG) else set()


def mark_long(bvid):
    seen = long_seen()
    seen.add(bvid)
    os.makedirs(os.path.dirname(LONG), exist_ok=True)
    json.dump(sorted(seen), open(LONG, "w"), ensure_ascii=False)


def to_pcm(url, dst, cap):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-user_agent", UA, "-headers", f"Referer: {REF}",
                    "-i", url, "-t", str(cap), "-vn", "-ac", "1", "-ar", "16000",
                    "-f", "s16le", dst], check=True, timeout=1800)


def transcribe(pcm, model_name="medium"):
    import numpy as np
    from faster_whisper import WhisperModel
    aud = np.fromfile(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    m = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=4)
    segs, info = m.transcribe(aud, language="zh", vad_filter=True, beam_size=5,
                              condition_on_previous_text=False)
    return "".join(s.text for s in segs).strip(), info.duration


def one(bvid, cap=1800, max_dur=0):
    out = os.path.join(ROOT, "transcripts", f"bilibili-{bvid}.txt")
    if os.path.exists(out) and os.path.getsize(out) > 40:
        return "SKIP", 0, bvid
    pages = pages_of(bvid)
    total = sum((p.get("duration") or 0) for p in pages)
    if max_dur and total > max_dur:
        mark_long(bvid)
        return "LONG", total, bvid
    parts = []
    for p in pages:
        cid, dur = p.get("cid"), p.get("duration") or 0
        u = audio_url(bvid, cid)
        if not u:
            continue
        with tempfile.TemporaryDirectory() as tmp:
            pcm = os.path.join(tmp, "a.pcm")
            to_pcm(u, pcm, min(dur or cap, cap))
            text, used = transcribe(pcm)
        parts.append(text)
        cap -= int(used)
        if cap <= 0:
            break
    text = "\n".join(x for x in parts if x)
    open(out, "w").write(text + "\n")
    if len(text) > 40:
        subprocess.run([sys.executable, os.path.join(ROOT, "attach_transcript.py"),
                        "bilibili", bvid, out], check=False,
                       stdout=subprocess.DEVNULL)
        return "OK", len(text), bvid
    return "EMPTY", 0, bvid


def todo(cap_seconds):
    items = [json.loads(l) for l in open(os.path.join(ROOT, "index", "items.jsonl")) if l.strip()]
    tr = {}
    tp = os.path.join(ROOT, "index", "transcripts.json")
    if os.path.exists(tp):
        tr = json.load(open(tp))
    out = []
    for it in items:
        if it.get("platform") != "bilibili":
            continue
        if f"bilibili:{it['id']}" in tr:
            continue
        if it["id"] in long_seen():
            continue
        out.append(it)
    return out


def main():
    args = sys.argv[1:]
    cap = 1800
    max_dur = 1200
    limit = None
    workers = 2
    for i, a in enumerate(args):
        if a == "--max-dur":
            max_dur = int(args[i + 1])
        elif a == "--cap":
            cap = int(args[i + 1])
        elif a == "--limit":
            limit = int(args[i + 1])
        elif a == "--workers":
            workers = int(args[i + 1])
    jobs = todo(cap)
    if limit:
        jobs = jobs[:limit]
    print(f"{len(jobs)} videos to transcribe, cap {cap}s each, "
          f"max length {max_dur or 'unlimited'}s, {len(long_seen())} long ones already skipped",
          flush=True)
    # simple worker pool: fork children over the job list
    import multiprocessing as mp
    pending = [j["id"] for j in jobs]
    with mp.Pool(workers) as pool:
        f = functools.partial(one, cap=cap, max_dur=max_dur)
        for status, n, bvid in pool.imap_unordered(f, pending):
            print(f"{status} {bvid} {n}", flush=True)


if __name__ == "__main__":
    main()

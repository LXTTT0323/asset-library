#!/usr/bin/env python3
"""Grab a signed media URL while it is still alive, and keep the audio.

Douyin and Xiaohongshu only expose signed CDN links inside a logged-in
browser, and they expire within minutes. So the browser side reports the URL
and this script downloads it immediately, throwing the video away and keeping
just 16k mono PCM in media/<platform>-<id>.pcm, ready for tools/asr_media.py.

Usage:
  python3 tools/fetch_media.py <platform> <item_id> <url>
  python3 tools/fetch_media.py --queue             # raw/media-queue.jsonl, the usual path
  python3 tools/fetch_media.py --file urls.txt      # lines: platform id url

Exit 0 and prints OK when media/<platform>-<id>.pcm exists.
"""
import json, os, subprocess, sys, tempfile

ROOT = os.environ.get("ASSET_LIB") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/156.0.0.0 Safari/537.36")
REFERERS = {
    "douyin": "https://www.douyin.com/",
    "xiaohongshu": "https://www.rednote.com/",
    "bilibili": "https://www.bilibili.com/",
}
CAP = 1800


def fetch(platform, item_id, url):
    out = os.path.join(ROOT, "media", f"{platform}-{item_id}.pcm")
    if os.path.exists(out) and os.path.getsize(out) > 16000:
        print(f"SKIP {platform} {item_id} 已有 PCM")
        return True
    os.makedirs(os.path.join(ROOT, "media"), exist_ok=True)
    ref = REFERERS.get(platform, REFERERS["douyin"])
    with tempfile.TemporaryDirectory() as tmp:
        media = os.path.join(tmp, "m")
        subprocess.run(["curl", "-sL", "-A", UA, "-e", ref, "-o", media, url],
                       check=True, timeout=600)
        size = os.path.getsize(media)
        if size < 20000:
            print(f"FAIL {platform} {item_id} 下载只有 {size} 字节,链接可能已过期")
            return False
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", media,
                        "-t", str(CAP), "-vn", "-ac", "1", "-ar", "16000",
                        "-f", "s16le", out], check=True, timeout=1800)
    secs = os.path.getsize(out) / 32000
    print(f"OK {platform} {item_id} {secs:.0f}s -> media/{platform}-{item_id}.pcm")
    return True


def from_queue(path=None):
    """Fetch every un-fetched line of raw/media-queue.jsonl (one JSON object per line)."""
    path = path or os.path.join(ROOT, "raw", "media-queue.jsonl")
    done_p = os.path.join(ROOT, "raw", ".fetched")
    if not os.path.exists(path):
        print("no queue")
        return
    done = set(open(done_p).read().split()) if os.path.exists(done_p) else set()
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = f"{d['platform']}:{d['id']}"
        if key in done:
            continue
        if fetch(d["platform"], str(d["id"]), d["url"]):
            open(done_p, "a").write(key + "\n")


def main():
    a = sys.argv[1:]
    if a and a[0] == "--queue":
        from_queue(a[1] if len(a) > 1 else None)
        return
    if a and a[0] == "--file":
        ok = 0
        for line in open(a[1]):
            parts = line.split()
            if len(parts) >= 3:
                ok += bool(fetch(parts[0], parts[1], " ".join(parts[2:])))
        print(f"完成 {ok} 条")
        return
    if len(a) < 3:
        print(__doc__)
        sys.exit(1)
    fetch(a[0], a[1], a[2])


if __name__ == "__main__":
    main()

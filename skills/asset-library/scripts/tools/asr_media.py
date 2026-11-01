#!/usr/bin/env python3
"""Transcribe local audio that was already pulled down by the browser.

Douyin and Xiaohongshu only give up their signed media links inside a logged-in
browser, and those links die in minutes. So the browser side runs

  ffmpeg -user_agent ... -headers "Referer: ..." -i "<signed url>" -t 1800 \\
         -vn -ac 1 -ar 16000 -f s16le media/<platform>-<id>.pcm

the moment it sees the stream. This script then turns those PCM files into
transcripts, attaches them to the item markdown, and deletes the PCM.

Usage:
  python3 tools/asr_media.py [--dir media] [--keep]

Without --keep the PCM file is removed after a successful transcript.
"""
import argparse, os, re, subprocess, sys

ROOT = os.environ.get("ASSET_LIB") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join(ROOT, "media"))
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args()
    if not os.path.isdir(a.dir):
        print(f"{a.dir} 不存在,没有待转的音频")
        return
    jobs = []
    for f in sorted(os.listdir(a.dir)):
        m = re.match(r"(.+?)-(.+)\.(pcm|mp4|m4a|mp3|wav)$", f)
        if not m:
            continue
        platform, item_id, ext = m.groups()
        out = os.path.join(ROOT, "transcripts", f"{platform}-{item_id}.txt")
        if os.path.exists(out) and os.path.getsize(out) > 40:
            continue
        jobs.append((platform, item_id, os.path.join(a.dir, f), ext))
    if not jobs:
        print("没有待转的音频")
        return
    print(f"{len(jobs)} 个待转")
    os.makedirs(os.path.join(ROOT, "transcripts"), exist_ok=True)
    import numpy as np
    from faster_whisper import WhisperModel
    model = WhisperModel("medium", device="cpu", compute_type="int8", cpu_threads=6)
    for platform, item_id, path, ext in jobs:
        pcm = path
        if ext != "pcm":
            pcm = path + ".pcm"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-vn",
                            "-ac", "1", "-ar", "16000", "-f", "s16le", pcm], check=True)
        aud = np.fromfile(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        segs, info = model.transcribe(aud, language="zh", vad_filter=True, beam_size=5,
                                      condition_on_previous_text=False)
        text = "".join(s.text for s in segs).strip()
        out = os.path.join(ROOT, "transcripts", f"{platform}-{item_id}.txt")
        open(out, "w").write(text + "\n")
        status = "EMPTY" if len(text) <= 40 else "OK"
        print(f"{status} {platform} {item_id} {len(text)} 字 / {info.duration:.0f}s", flush=True)
        if status == "OK":
            subprocess.run([sys.executable, os.path.join(ROOT, "lib.py"), "attach",
                            platform, item_id, out], check=False, stdout=subprocess.DEVNULL)
        if not a.keep:
            for p in {path, pcm}:
                if os.path.exists(p):
                    os.remove(p)


if __name__ == "__main__":
    main()

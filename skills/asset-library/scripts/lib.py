#!/usr/bin/env python3
"""One-file library CLI. Subcommands: classify, ingest, report, topics, attach, prune, digest, stats.

The library root is $ASSET_LIB, else the directory holding this file.
Layout: topics.json, items/<platform>/, index/, raw/, reports/, transcripts/, media/.
"""
import collections, datetime, json, os, re, sys

ROOT = os.environ.get("ASSET_LIB") or os.path.dirname(os.path.abspath(__file__))
IDX = os.path.join(ROOT, "index")
CORE = ("platform", "id", "title", "author", "url", "likes", "collects", "comments",
        "plays", "published_at", "kind", "captured_at")
MD = ("author", "url", "published_at", "kind", "likes", "collects", "comments", "plays", "cover")
FALLBACK_STRONG = ["ai", "人工智能", "大模型", "模型", "gpt", "claude", "gemini", "grok",
                   "codex", "cursor", "agent", "提示词", "prompt"]


def cfg():
    return json.load(open(os.path.join(ROOT, "topics.json")))


def words(key, default=()):
    return [str(s).lower() for s in (cfg().get(key) or default)]


def keep(blob, inc, exc, strong):
    b = (blob or "").lower()
    return any(w in b for w in inc) and (not any(w in b for w in exc) or any(w in b for w in strong))


def rows(path=None):
    p = path or os.path.join(IDX, "items.jsonl")
    return [json.loads(l) for l in open(p) if l.strip()] if os.path.exists(p) else []


def num(v):
    """Sort key for counts: 1234, '9.8万', '1.2w', '3k', '1,234'. Unknown -> 0."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    t = str(v or "").replace(",", "").replace("，", "").strip()
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*([万wW千kK]?)", t)
    if not m:
        return 0.0
    return float(m.group(1)) * (10000 if m.group(2) in "万wW" and m.group(2) else 1000 if m.group(2) in "千kK" and m.group(2) else 1)


def slug(s, n=40):
    return (re.sub(r"[^\w\u4e00-\u9fff]+", "-", s or "untitled").strip("-") or "untitled")[:n]


def item_md(platform, item_id):
    d = os.path.join(ROOT, "items", platform)
    if not os.path.isdir(d):
        return ""
    for f in sorted(os.listdir(d)):
        if f.startswith(str(item_id)):
            return open(os.path.join(d, f)).read()
    return ""


# ---- classify -------------------------------------------------------------
def cmd_classify(args):
    path = [a for a in args if not a.startswith("-")][0]
    data = json.load(open(path))
    items = data.get("items") if isinstance(data, dict) else data
    inc, exc, strong = words("include"), words("exclude"), words("strong", FALLBACK_STRONG)
    kept = [i for i in items if keep(f"{i.get('title') or ''} {i.get('text') or ''}", inc, exc, strong)]
    out = dict(data) if isinstance(data, dict) else {}
    out["items"] = kept
    op = path[:-5] + ".filtered.json" if path.endswith(".json") else path + ".filtered.json"
    json.dump(out, open(op, "w"), ensure_ascii=False, indent=1)
    print(f"kept {len(kept)}, dropped {len(items) - len(kept)} of {len(items)} -> {op}")
    if "-v" in args:
        for i in items:
            if i not in kept:
                print("  DROP", (i.get("title") or "")[:50])


# ---- ingest ---------------------------------------------------------------
def cmd_ingest(args):
    platform, path = args[0], args[1]
    items = json.load(open(path))
    if isinstance(items, dict):
        items = items.get("items") or []
    os.makedirs(IDX, exist_ok=True)
    seenp = os.path.join(IDX, "seen.json")
    seen = json.load(open(seenp)) if os.path.exists(seenp) else {}
    d = os.path.join(ROOT, "items", platform)
    os.makedirs(d, exist_ok=True)
    new = 0
    for it in items:
        iid = str(it.get("id") or slug(it.get("title"), 12))
        key = f"{platform}:{iid}"
        if key in seen:
            continue
        it.update(id=iid, platform=platform)
        it.setdefault("captured_at", datetime.datetime.now().isoformat(timespec="seconds"))
        fn = os.path.join(d, f"{iid}-{slug(it.get('title'))}.md")
        with open(fn, "w") as f:
            f.write(f"# {it.get('title', '')}\n\n")
            for k in MD:
                if it.get(k) not in (None, ""):
                    f.write(f"- **{k}**: {it[k]}\n")
            f.write(f"- **captured_at**: {it['captured_at']}\n")
            extra = sorted((k for k in it if k not in CORE and k not in MD and k != "text"
                            and it[k] not in (None, "", [], {})),
                           key=lambda k: (k != "cover", k != "shares", k))
            for k in extra:
                f.write(f"- **{k}**: {it[k]}\n")
            f.write(f"\n---\n\n{it.get('text') or ''}\n")
        seen[key] = os.path.relpath(fn, ROOT)
        rec = {k: it.get(k) for k in CORE}
        rec.update({k: v for k, v in it.items()
                    if k not in CORE and k != "text" and v not in (None, "", [], {})})
        with open(os.path.join(IDX, "items.jsonl"), "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        new += 1
    json.dump(seen, open(seenp, "w"), ensure_ascii=False, indent=1)
    print(f"{platform}: {new} new, {len(items) - new} already known, {len(seen)} tracked")


# ---- report ---------------------------------------------------------------
def cmd_report(_args):
    rs = rows()
    by = collections.defaultdict(list)
    for r in rs:
        by[r.get("platform") or "?"].append(r)
    out = ["# 素材库快照", "", f"共 {len(rs)} 条,分布在 {len(by)} 个平台。", ""]
    for p, prs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        out += [f"## {p} — {len(prs)} 条", ""]
        for r in prs[:60]:
            t = (r.get("title") or "").replace("\n", " ")[:70]
            lk = f" · {r['likes']} 赞" if r.get("likes") not in (None, "") else ""
            out.append(f"- {t} — {r.get('author') or ''}{lk}")
            if r.get("url"):
                out.append(f"  {r['url']}")
        if len(prs) > 60:
            out.append(f"- …还有 {len(prs) - 60} 条")
        out.append("")
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    p = os.path.join(ROOT, "reports", "snapshot.md")
    open(p, "w").write("\n".join(out))
    print(p, len(out), "lines")


# ---- topics ---------------------------------------------------------------
def bucket_of(title, text, buckets):
    """Score buckets on the title; fall back to the body only when the title hits nothing."""
    prio = {b["key"]: b.get("priority", 999) for b in buckets}
    kw = {b["key"]: [str(w).lower() for w in (b.get("keywords") or [])] for b in buckets}
    order = {b["key"]: i for i, b in enumerate(buckets)}

    def score(s):
        s = (s or "").lower()
        flat = s.replace(" ", "").replace("\u3000", "")
        return [(sum(1 for w in kw[b["key"]] if w in s or w.replace(" ", "") in flat),
                 prio[b["key"]], b["key"]) for b in buckets]

    got = [x for x in score(title) if x[0]] or [x for x in score(text) if x[0]]
    if not got:
        return []
    got.sort(key=lambda x: (-x[0], x[1], order[x[2]]))
    top = got[0][0]
    return [k for n, _, k in got if n >= top - 1][:2] if top >= 2 else [got[0][2]]


def fmt(r, n=64):
    t = (r.get("title") or "").replace("\n", " ")[:n]
    lk = f" · {r['likes']} 赞" if r.get("likes") not in (None, "") else ""
    return f"- {f'[{t}]({r['url']})' if r.get('url') else t} — {r.get('author') or ''}{lk} ({r.get('platform') or ''})"


def cmd_topics(_args):
    buckets = cfg().get("buckets")
    if not buckets:
        print('topics.json 里没有 "buckets"，跳过')
        return
    out = []
    for r in rows():
        out.append({**r, "topics": bucket_of(r.get("title"), r.get("text"), buckets) or ["other"]})
    os.makedirs(os.path.join(ROOT, "reports", "topics"), exist_ok=True)
    with open(os.path.join(IDX, "topics.jsonl"), "w") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    names = {b["key"]: b["label"] for b in buckets}
    names["other"] = "未归类"
    sections = [(b["key"], names[b["key"]]) for b in buckets] + [("other", names["other"])]
    brief = ["# 素材库 · 按主题", "", f"共 {len(out)} 条，按关键词命中强度归入最贴切的一到两个主题，每个主题按点赞从高到低排。", ""]
    full = ["# 素材库 · 全量分主题清单", "", f"共 {len(out)} 条，分布在 {len(buckets)} 个主题。", ""]
    for key, label in sections:
        rs = sorted((r for r in out if key in r["topics"]), key=lambda r: -num(r.get("likes")))
        brief += [f"## {label} — {len(rs)} 条", ""]
        brief += [fmt(r) for r in rs[:15]] or ["- （无）"]
        if len(rs) > 15:
            brief.append(f"- 其余 {len(rs) - 15} 条见 `reports/topics/{key}.md`")
        brief.append("")
        full += [f"## {label} — {len(rs)} 条", ""] + ([fmt(r, 200) for r in rs] or ["- （无）"]) + [""]
        open(os.path.join(ROOT, "reports", "topics", f"{key}.md"), "w").write(
            "\n".join([f"# {label}（{len(rs)} 条，按点赞排序）", ""] + [fmt(r, 200) for r in rs]) + "\n")
    open(os.path.join(ROOT, "reports", "by-topic.md"), "w").write("\n".join(brief))
    open(os.path.join(ROOT, "reports", "by-topic-full.md"), "w").write("\n".join(full))
    print("reports/by-topic.md, reports/by-topic-full.md, reports/topics/<key>.md")
    for key, label in sections:
        print(f"  {label}: {sum(1 for r in out if key in r['topics'])}")


# ---- attach ---------------------------------------------------------------
def cmd_attach(args):
    platform, item_id, path = args[:3]
    text = open(path).read().strip()
    if not text:
        print("EMPTY")
        return
    p = os.path.join(ROOT, "items", platform,
                     next((f for f in sorted(os.listdir(os.path.join(ROOT, "items", platform)))
                           if f.startswith(str(item_id))), ""))
    if not os.path.isfile(p):
        print("NO_ITEM")
        return
    s = open(p).read()
    head = "## 口播文字稿"
    s = (s.split(head)[0].rstrip() if head in s else s.rstrip()) + f"\n\n{head}\n\n{text}\n"
    open(p, "w").write(s)
    tp = os.path.join(IDX, "transcripts.json")
    d = json.load(open(tp)) if os.path.exists(tp) else {}
    d[f"{platform}:{item_id}"] = text
    json.dump(d, open(tp, "w"), ensure_ascii=False, indent=1)
    print("OK", os.path.basename(p), len(text))


# ---- prune ----------------------------------------------------------------
def cmd_prune(args):
    inc, exc, strong = words("include"), words("exclude"), words("strong", FALLBACK_STRONG)
    prot = set()
    pp = os.path.join(IDX, "curated_ids.json")
    if os.path.exists(pp):
        prot = set(json.load(open(pp)))
    seenp = os.path.join(IDX, "seen.json")
    seen = json.load(open(seenp)) if os.path.exists(seenp) else {}
    keepers, droppers = [], []
    for r in rows():
        (keepers if keep(f"{r.get('title') or ''} {r.get('text') or ''}", inc, exc, strong)
         or r.get("id") in prot else droppers).append(r)
    print(f"keep {len(keepers)}, drop {len(droppers)}, total {len(keepers) + len(droppers)}")
    for r in droppers:
        print("  DROP", r.get("platform"), (r.get("title") or "")[:50])
    if "--apply" not in args:
        return
    for r in droppers:
        p = seen.pop(f"{r['platform']}:{r['id']}", None)
        p = os.path.join(ROOT, p) if p and not os.path.isabs(p) else p
        if p and os.path.exists(p):
            os.remove(p)
    with open(os.path.join(IDX, "items.jsonl"), "w") as f:
        for r in keepers:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    json.dump(seen, open(seenp, "w"), ensure_ascii=False, indent=1)
    print("applied")


# ---- digest ---------------------------------------------------------------
def cmd_digest(args):
    date = next((a for a in args if re.match(r"^\d{4}-\d{2}-\d{2}$", a)), datetime.date.today().isoformat())
    head, tail, out = 1600, 400, ""
    for i, a in enumerate(args):
        if a == "--head":
            head = int(args[i + 1])
        elif a == "--tail":
            tail = int(args[i + 1])
        elif a == "--out":
            out = args[i + 1]
    tr = {}
    tp = os.path.join(IDX, "transcripts.json")
    if os.path.exists(tp):
        tr = json.load(open(tp))
    tmap = {f"{r.get('platform')}:{r.get('id')}": r.get("topics") or [] for r in rows(os.path.join(IDX, "topics.jsonl"))}
    today = sorted((r for r in rows() if (r.get("captured_at") or "").startswith(date)),
                   key=lambda r: -num(r.get("likes")))
    lines = [f"# {date} 新增素材 {len(today)} 条", ""]
    for i, r in enumerate(today, 1):
        key = f"{r['platform']}:{r['id']}"
        md = item_md(r["platform"], r["id"])
        body = md.split("---", 1)[1].strip() if "---" in md else md.strip()
        text = tr.get(key) or body
        text = " ".join(text.split())
        if len(text) > head + tail:
            text = text[:head] + " …(中略)… " + text[-tail:]
        src = "口播转写" if key in tr else ("图文正文" if r.get("kind") != "video" else "无转写,只有标题")
        lines += [f"## {i}. {r.get('title') or '(无标题)'}",
                  f"- 平台 {r['platform']} · 作者 {r.get('author') or '?'} · 赞 {r.get('likes')} · 类型 {r.get('kind')}"]
        if tmap.get(key):
            lines.append(f"- 主题 {', '.join(tmap[key])}")
        lines += [f"- 链接 {r.get('url')}", f"- 文字来源 {src}", "", text or "(没有可读文字)", ""]
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    p = out or os.path.join(ROOT, "reports", f"digest-pack-{date}.md")
    open(p, "w").write("\n".join(lines))
    print(f"{p}  {len(today)} 条，其中 {sum(1 for r in today if f'{r['platform']}:{r['id']}' in tr)} 条有口播转写")


# ---- stats ----------------------------------------------------------------
def cmd_stats(_args):
    vids = [r for r in rows() if r.get("kind") == "video"]
    tr = {}
    p = os.path.join(IDX, "transcripts.json")
    if os.path.exists(p):
        tr = json.load(open(p))
    have = [r for r in vids if f"{r['platform']}:{r['id']}" in tr]
    print(f"视频 {len(vids)} 条，有文字稿 {len(have)} 条，缺 {len(vids) - len(have)} 条")
    per, got = collections.Counter(r["platform"] for r in vids), collections.Counter(r["platform"] for r in have)
    for k, n in per.most_common():
        print(f"  {k:12} {got.get(k, 0)}/{n}")
    print(f"文字稿共 {sum(len(v) for v in tr.values()) / 10000:.1f} 万字")


CMDS = {"classify": cmd_classify, "ingest": cmd_ingest, "report": cmd_report, "topics": cmd_topics,
        "attach": cmd_attach, "prune": cmd_prune, "digest": cmd_digest, "stats": cmd_stats}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print(__doc__)
        sys.exit(1)
    CMDS[sys.argv[1]](sys.argv[2:])

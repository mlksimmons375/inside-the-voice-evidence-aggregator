#!/usr/bin/env python3
"""
Evidence Aggregator - Local Web App
===================================

A small Flask app you run on your own machine to drive the Evidence Aggregator
from the browser instead of the command line, then curate what comes back.

    python app.py
    -> open http://127.0.0.1:5000

Flow:
    1. Pick an episode number, topic, and which sources to gather.
    2. Hit Gather. Watch the live log. (Runs in a background thread.)
    3. When it's done, open the episode to curate: for each piece of evidence,
       tag it to Claim 1 / 2 / 3 or Cut it, and add a note.
    4. Export a clean curated_evidence.md grouped by claim.

Single user, local only. No auth, no database - curation is saved as
curation.json next to each episode's evidence_data.json.
"""

import json
import threading
from pathlib import Path

from flask import (Flask, request, redirect, url_for, jsonify,
                   render_template, send_file, abort)

import evidence_aggregator as ea

app = Flask(__name__)

# The three claims every episode argues (from the method docs).
CLAIMS = {
    "1": "Claim 1 - The problem exists",
    "2": "Claim 2 - The belief is incomplete / fails",
    "3": "Claim 3 - The corrected version (the real answer)",
}

# Single in-memory job (single user, one run at a time).
JOB = {"running": False, "log": [], "episode": None, "error": None, "done": False}
_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Gathering (background thread)
# ---------------------------------------------------------------------------
def _run_job(episode_num, topic, queries, sources):
    def progress(msg):
        with _LOCK:
            JOB["log"].append(msg)
    try:
        agg = ea.EvidenceAggregator(episode_num, topic, queries=queries or None)
        with _LOCK:
            JOB["episode"] = agg.base_dir.name
        agg.run(sources, progress=progress)
    except Exception as e:  # last-resort guard; individual sources already fail soft
        with _LOCK:
            JOB["error"] = str(e)
            JOB["log"].append(f"FATAL: {e}")
    finally:
        with _LOCK:
            JOB["running"] = False
            JOB["done"] = True


@app.route("/")
def index():
    episodes = _list_episodes()
    return render_template("index.html",
                           topics=list(ea.TOPIC_QUERIES.keys()),
                           sources=ea.SOURCE_ORDER,
                           episodes=episodes,
                           running=JOB["running"])


@app.route("/run", methods=["POST"])
def run():
    if JOB["running"]:
        return redirect(url_for("index"))
    try:
        episode_num = int(request.form.get("episode", "1"))
    except ValueError:
        episode_num = 1
    topic = (request.form.get("topic") or "").strip() or "untitled"
    queries = [q.strip() for q in (request.form.get("queries") or "").splitlines() if q.strip()]
    sources = [s for s in ea.SOURCE_ORDER if request.form.get(f"src_{s}")]
    if not sources:
        sources = ["reddit", "youtube", "clips", "transcripts", "articles", "scholar"]

    with _LOCK:
        JOB.update(running=True, log=[], episode=None, error=None, done=False)
    threading.Thread(target=_run_job,
                     args=(episode_num, topic, queries, sources),
                     daemon=True).start()
    return redirect(url_for("index"))


@app.route("/status")
def status():
    with _LOCK:
        return jsonify(running=JOB["running"], done=JOB["done"],
                       episode=JOB["episode"], error=JOB["error"],
                       log=JOB["log"][-400:])


# ---------------------------------------------------------------------------
# Curation
# ---------------------------------------------------------------------------
@app.route("/episode/<name>")
def episode(name):
    base = _safe_episode_dir(name)
    data = _load_json(base / "evidence_data.json")
    if data is None:
        abort(404)
    curation = _load_json(base / "curation.json") or {}
    cards = _build_cards(data, base)
    # attach curation state
    for c in cards:
        state = curation.get(c["id"], {})
        c["claim"] = state.get("claim", "")
        c["note"] = state.get("note", "")
    counts = {k: sum(1 for c in cards if c["claim"] == k) for k in CLAIMS}
    counts["cut"] = sum(1 for c in cards if c["claim"] == "cut")
    return render_template("episode.html", name=name, data=data, cards=cards,
                           claims=CLAIMS, counts=counts)


@app.route("/curate", methods=["POST"])
def curate():
    payload = request.get_json(force=True)
    name = payload["episode"]
    base = _safe_episode_dir(name)
    path = base / "curation.json"
    curation = _load_json(path) or {}
    entry = curation.get(payload["id"], {})
    if "claim" in payload:
        entry["claim"] = payload["claim"]
    if "note" in payload:
        entry["note"] = payload["note"]
    curation[payload["id"]] = entry
    path.write_text(json.dumps(curation, indent=2, ensure_ascii=False), encoding="utf-8")
    return jsonify(ok=True)


@app.route("/export/<name>", methods=["POST"])
def export(name):
    base = _safe_episode_dir(name)
    data = _load_json(base / "evidence_data.json")
    if data is None:
        abort(404)
    curation = _load_json(base / "curation.json") or {}
    cards = _build_cards(data, base)
    by_id = {c["id"]: c for c in cards}

    lines = [f"# Curated Evidence - Episode {data.get('episode')}: {data.get('topic')}", ""]
    for key, label in CLAIMS.items():
        kept = [by_id[i] for i, st in curation.items()
                if st.get("claim") == key and i in by_id]
        lines.append(f"## {label}  ({len(kept)})\n")
        if not kept:
            lines.append("_(nothing assigned yet)_\n")
        for c in kept:
            lines.append(f"### {c['title']}")
            if c["subtitle"]:
                lines.append(f"*{c['subtitle']}*")
            if c["url"]:
                lines.append(f"{c['url']}")
            if c["body"]:
                lines.append(f"\n> {c['body'][:800]}")
            note = curation.get(c["id"], {}).get("note", "")
            if note:
                lines.append(f"\n**Note:** {note}")
            lines.append("")
        lines.append("")

    out = base / "curated_evidence.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return send_file(out, as_attachment=True, download_name=f"{name}_curated.md")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _list_episodes():
    root = ea.EPISODES_ROOT
    if not root.exists():
        return []
    out = []
    for d in sorted(root.iterdir()):
        if (d / "evidence_data.json").exists():
            data = _load_json(d / "evidence_data.json") or {}
            s = data.get("sources", {})
            counts = {k: len(v) for k, v in s.items()}
            counts["transcripts"] = sum(1 for c in s.get("clips", []) if c.get("has_transcript"))
            out.append({
                "name": d.name,
                "topic": data.get("topic", ""),
                "generated": data.get("generated", ""),
                "counts": counts,
            })
    return out


def _safe_episode_dir(name):
    """Resolve an episode dir, refusing anything outside EPISODES_ROOT."""
    base = (ea.EPISODES_ROOT / name).resolve()
    if ea.EPISODES_ROOT.resolve() not in base.parents or not base.is_dir():
        abort(404)
    return base


def _load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def _build_cards(data, base=None):
    """Flatten every source's items into uniform display cards with stable ids.
    If `base` is given, clip cards load their transcript text so the coach's
    actual words show up in the card (that's the point of pulling them)."""
    cards = []
    s = data.get("sources", {})

    for i, p in enumerate(s.get("reddit", [])):
        body = p.get("selftext", "")
        if p.get("top_comments"):
            body += "\n\nTop comments:\n" + "\n".join(
                f"({c['score']}) {c['body']}" for c in p["top_comments"][:3])
        cards.append(_card("reddit", i, p.get("title", ""),
                           f"r/{p.get('subreddit','')} - {p.get('score',0)} upvotes",
                           body, p.get("url", "")))

    for i, c in enumerate(s.get("youtube_comments", [])):
        cards.append(_card("youtube", i,
                           f"{c.get('author','')} ({c.get('likes',0)} likes)",
                           c.get("video_title", ""), c.get("text", ""),
                           c.get("video_url", "")))

    for i, c in enumerate(s.get("clips", [])):
        sub = c.get("query", "")
        body = c.get("description", "")
        tf = c.get("transcript_file")
        if c.get("has_transcript") and tf and base is not None:
            sub += " - has transcript"
            try:
                raw = (base / "Clips" / "transcripts" / tf).read_text(
                    encoding="utf-8", errors="ignore")
                parts = raw.split("=" * 80, 1)          # strip the file header
                txt = (parts[1] if len(parts) > 1 else raw).strip()
                body = "TRANSCRIPT:\n" + txt[:6000]
            except Exception:
                pass
        cards.append(_card("clips", i, c.get("title", ""), sub, body, c.get("url", "")))

    for i, a in enumerate(s.get("articles", [])):
        cards.append(_card("articles", i, a.get("title", ""),
                           a.get("source", ""), "", a.get("url", "")))

    for i, p in enumerate(s.get("research", [])):
        cards.append(_card("research", i, p.get("title", ""),
                           f"{p.get('year','')} - {p.get('citations',0)} citations",
                           p.get("abstract", ""), p.get("url", "")))
    return cards


def _card(source, idx, title, subtitle, body, url):
    return {"id": f"{source}:{idx}", "source": source, "title": title or "(untitled)",
            "subtitle": subtitle or "", "body": body or "", "url": url or ""}


if __name__ == "__main__":
    # 0.0.0.0 so it's reachable from the Windows browser when run inside WSL2
    # (WSL2 forwards localhost; binding all interfaces is the robust choice).
    # Open http://127.0.0.1:5000 (or http://localhost:5000) in your browser.
    print("Evidence Aggregator web app -> http://127.0.0.1:5000  (Ctrl+C to stop)")
    app.run(host="0.0.0.0", port=5000, debug=False)

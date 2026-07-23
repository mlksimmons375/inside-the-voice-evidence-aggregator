#!/usr/bin/env python3
"""
Evidence Aggregator v3.0 - Inside The Voice
============================================

One clean, unified script (merges the old A/yt-dlp and B/api versions and adds
Reddit). Personal, single-user, local tool. Gathers the raw evidence for one
episode from several sources, then you hand the dumps to Claude to curate into
the episode's three claims:

    Claim 1  the problem exists        <- Reddit, YouTube comments, sameness of advice
    Claim 2  the belief is incomplete  <- research papers, expert articles, transcripts
    Claim 3  the corrected version     <- research papers, physiology, transcripts

Sources (each fails gracefully - one dead source never kills the run):
    reddit       posts + top comments from vocal subreddits          (praw)
    youtube      comments from videos matching each query            (YouTube Data API)
    clips        finds videos + writes their URLs                    (YouTube Data API)
    transcripts  transcript text for the found clips                 (youtube-transcript-api, yt-dlp fallback)
    articles     web articles + expert-site hits                     (DuckDuckGo, no key)
    scholar      research papers                                     (scholarly)

CLI:
    python evidence_aggregator.py --episode 1 --topic warmup \
        --reddit --youtube --clips --transcripts --articles --scholar

Or drive it from the local web app:  python app.py

Credentials (environment variables, never hardcoded):
    YOUTUBE_API_KEY           - required for --youtube / --clips
    REDDIT_CLIENT_ID          - required for --reddit
    REDDIT_CLIENT_SECRET      - required for --reddit
    REDDIT_USER_AGENT         - optional (a default is provided)
    REDDIT_SUBREDDITS         - optional, comma-separated (default: singing,vocalcoaching)

See SETUP.md for how to install deps and get the keys.
"""

import os
import re
import json
import time
import argparse
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

# ---------------------------------------------------------------------------
# Optional dependencies. Each is guarded so a missing library disables only its
# own source instead of crashing the whole tool.
# ---------------------------------------------------------------------------
try:
    import praw
    REDDIT_AVAILABLE = True
except ImportError:
    REDDIT_AVAILABLE = False

try:
    from googleapiclient.discovery import build as _yt_build
    YOUTUBE_AVAILABLE = True
except ImportError:
    YOUTUBE_AVAILABLE = False

try:
    import requests
    from bs4 import BeautifulSoup
    WEB_AVAILABLE = True
except ImportError:
    WEB_AVAILABLE = False

try:
    from scholarly import scholarly
    SCHOLAR_AVAILABLE = True
except ImportError:
    SCHOLAR_AVAILABLE = False

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    TRANSCRIPT_API_AVAILABLE = True
except ImportError:
    TRANSCRIPT_API_AVAILABLE = False

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
APP_ROOT = Path(__file__).resolve().parent
EPISODES_ROOT = APP_ROOT / "episodes"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# The source pipeline order. transcripts intentionally runs after clips so it
# has videos to work with.
SOURCE_ORDER = ["reddit", "youtube", "clips", "transcripts", "articles", "scholar"]

TOPIC_QUERIES = {
    "breath": [
        "breath control singing", "running out of breath singing",
        "breath support singing", "can't finish phrases singing",
        "breathing exercises singing", "diaphragm singing technique",
        "vocal stamina breathing",
    ],
    "high-notes": [
        "high notes singing tight", "can't hit high notes",
        "high notes strained", "head voice vs chest voice",
        "passaggio break", "high notes feel squeezed",
        "hitting high notes technique",
    ],
    "tension": [
        "throat tension singing", "jaw tension singing",
        "vocal tension relief", "tongue tension singing",
        "relaxed singing technique", "releasing vocal tension",
        "tight throat singing",
    ],
    "warmup": [
        "how to warm up your voice singing", "vocal warm up before singing",
        "do i need to warm up my voice", "vocal warm up mistakes",
        "singing warm up routine how long", "warming up voice when sick or tired",
        "best vocal warm ups for singers",
    ],
}

DEFAULT_SUBREDDITS = ["singing", "vocalcoaching"]

# Expert vocal-pedagogy sites to target in the article search.
EXPERT_SITES = ["nats.org", "voicecouncil.com", "singwise.com", "bostonvoice.com"]


def slugify(text, maxlen=60):
    """Filesystem-safe, human-readable slug."""
    keep = "".join(c for c in text if c.isalnum() or c in (" ", "-", "_")).strip()
    return keep[:maxlen] if keep else "untitled"


class EvidenceAggregator:
    def __init__(self, episode_num, topic, queries=None, subreddits=None):
        self.episode_num = int(episode_num)
        self.topic = str(topic).lower().strip()

        # Search queries: explicit list > predefined topic > single fallback.
        if queries:
            self.search_queries = [q for q in queries if q.strip()]
        elif self.topic in TOPIC_QUERIES:
            self.search_queries = list(TOPIC_QUERIES[self.topic])
        else:
            self.search_queries = [f"{self.topic} singing"]

        env_subs = os.getenv("REDDIT_SUBREDDITS", "")
        self.subreddits = (
            subreddits
            or ([s.strip() for s in env_subs.split(",") if s.strip()] if env_subs else None)
            or list(DEFAULT_SUBREDDITS)
        )

        # Folder layout (created eagerly). Rooted at the script's folder so it
        # works the same whether run from CLI or the web app.
        safe_topic = self.topic.replace(" ", "_")
        self.base_dir = EPISODES_ROOT / f"Episode_{self.episode_num:02d}_{safe_topic}"
        self.evidence_dir = self.base_dir / "Evidence"
        self.research_dir = self.base_dir / "Research"
        self.clips_dir = self.base_dir / "Clips"
        self.transcripts_dir = self.clips_dir / "transcripts"
        for d in (self.evidence_dir, self.research_dir, self.clips_dir, self.transcripts_dir):
            d.mkdir(parents=True, exist_ok=True)

        self.results = {
            "episode": self.episode_num,
            "topic": self.topic,
            "search_queries": self.search_queries,
            "subreddits": self.subreddits,
            "generated": datetime.now().isoformat(timespec="seconds"),
            "sources": {
                "reddit": [], "youtube_comments": [], "clips": [],
                "articles": [], "research": [],
            },
        }

        self._progress = None  # optional callback(str) set by run()

        self.youtube = None
        if YOUTUBE_AVAILABLE and os.getenv("YOUTUBE_API_KEY"):
            try:
                self.youtube = _yt_build("youtube", "v3", developerKey=os.getenv("YOUTUBE_API_KEY"))
            except Exception as e:
                self._log(f"YouTube client init failed: {str(e)[:120]}")

    # -- logging ------------------------------------------------------------
    def _log(self, msg):
        print(msg, flush=True)
        if self._progress:
            try:
                self._progress(str(msg))
            except Exception:
                pass

    # -- orchestration ------------------------------------------------------
    def run(self, sources, progress=None):
        """Run the requested sources in the correct order, fail-soft, then
        write the report. `sources` is an iterable of names from SOURCE_ORDER."""
        self._progress = progress
        dispatch = {
            "reddit": self.search_reddit,
            "youtube": self.search_youtube_comments,
            "clips": self.search_video_clips,
            "transcripts": self.fetch_transcripts,
            "articles": self.search_google_articles,
            "scholar": self.search_google_scholar,
        }
        wanted = [s for s in SOURCE_ORDER if s in set(sources)]
        for s in wanted:
            self._log("\n" + "=" * 70)
            self._log(f"SOURCE: {s}")
            self._log("=" * 70)
            try:
                dispatch[s]()
            except Exception as e:  # never let one source kill the run
                self._log(f"[{s}] crashed and was skipped: {str(e)[:150]}")
        self.generate_report()
        self._progress = None
        return self.results

    # -- Reddit -------------------------------------------------------------
    def search_reddit(self):
        if not REDDIT_AVAILABLE:
            self._log("Reddit: praw not installed (pip install praw) - skipping.")
            return
        cid = os.getenv("REDDIT_CLIENT_ID")
        csecret = os.getenv("REDDIT_CLIENT_SECRET")
        uagent = os.getenv("REDDIT_USER_AGENT",
                           "inside-the-voice-evidence-aggregator/3.0")
        if not (cid and csecret):
            self._log("Reddit: REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not set - skipping. "
                      "See SETUP.md.")
            return
        try:
            reddit = praw.Reddit(client_id=cid, client_secret=csecret,
                                 user_agent=uagent, check_for_async=False)
            reddit.read_only = True
        except Exception as e:
            self._log(f"Reddit: client init failed ({str(e)[:100]}) - skipping.")
            return

        subs = "+".join(self.subreddits)
        posts = []
        for query in self.search_queries:
            self._log(f"Reddit: searching r/{subs} for '{query}'...")
            try:
                for sub in reddit.subreddit(subs).search(query, sort="relevance",
                                                          time_filter="all", limit=8):
                    top_comments = []
                    try:
                        sub.comment_sort = "top"
                        sub.comments.replace_more(limit=0)
                        for c in list(sub.comments)[:5]:
                            body = (c.body or "").strip()
                            if body and body not in ("[deleted]", "[removed]"):
                                top_comments.append({"body": body[:600], "score": int(c.score)})
                    except Exception:
                        pass
                    posts.append({
                        "title": sub.title,
                        "url": f"https://www.reddit.com{sub.permalink}",
                        "subreddit": str(sub.subreddit),
                        "score": int(sub.score),
                        "num_comments": int(sub.num_comments),
                        "selftext": (sub.selftext or "")[:1000],
                        "top_comments": top_comments,
                        "query": query,
                    })
            except Exception as e:
                self._log(f"Reddit query '{query}' failed: {str(e)[:100]}")
                continue

        # dedupe by url, rank by score
        seen, deduped = set(), []
        for p in posts:
            if p["url"] not in seen:
                seen.add(p["url"])
                deduped.append(p)
        deduped.sort(key=lambda p: p["score"], reverse=True)
        self.results["sources"]["reddit"] = deduped
        self._log(f"Reddit: {len(deduped)} unique posts.")

        out = self.evidence_dir / "reddit.txt"
        with open(out, "w", encoding="utf-8") as f:
            for p in deduped:
                f.write(f"[r/{p['subreddit']}] {p['title']}\n")
                f.write(f"SCORE: {p['score']} upvotes | {p['num_comments']} comments\n")
                f.write(f"URL: {p['url']}\n")
                f.write(f"QUERY: '{p['query']}'\n")
                if p["selftext"]:
                    f.write(f"\nPOST:\n{p['selftext']}\n")
                if p["top_comments"]:
                    f.write("\nTOP COMMENTS:\n")
                    for c in p["top_comments"]:
                        f.write(f"  ({c['score']}) {c['body']}\n")
                f.write("\n" + "=" * 80 + "\n\n")

    # -- YouTube comments ---------------------------------------------------
    def search_youtube_comments(self):
        if not self.youtube:
            self._log("YouTube: API not configured (set YOUTUBE_API_KEY) - skipping.")
            return
        all_comments = []
        for query in self.search_queries:
            self._log(f"YouTube comments: '{query}'...")
            try:
                search = self.youtube.search().list(
                    q=query, part="id,snippet", maxResults=5,
                    type="video", relevanceLanguage="en").execute()
                for item in search.get("items", []):
                    vid = item["id"]["videoId"]
                    title = item["snippet"]["title"]
                    try:
                        threads = self.youtube.commentThreads().list(
                            part="snippet", videoId=vid, maxResults=10,
                            order="relevance").execute()
                        for c in threads.get("items", []):
                            sn = c["snippet"]["topLevelComment"]["snippet"]
                            all_comments.append({
                                "video_title": title,
                                "video_url": f"https://youtube.com/watch?v={vid}",
                                "author": sn["authorDisplayName"],
                                "text": sn["textDisplay"],
                                "likes": int(sn.get("likeCount", 0)),
                                "query": query,
                            })
                    except Exception:
                        continue  # comments disabled etc.
            except Exception as e:
                self._log(f"YouTube query '{query}' failed: {str(e)[:100]}")
                continue

        all_comments.sort(key=lambda c: c["likes"], reverse=True)
        self.results["sources"]["youtube_comments"] = all_comments
        self._log(f"YouTube: {len(all_comments)} comments.")

        out = self.evidence_dir / "youtube_comments.txt"
        with open(out, "w", encoding="utf-8") as f:
            for c in all_comments:
                f.write(f"VIDEO: {c['video_title']}\n")
                f.write(f"URL: {c['video_url']}\n")
                f.write(f"QUERY: '{c['query']}'\n")
                f.write(f"AUTHOR: {c['author']} ({c['likes']} likes)\n\n")
                f.write(f"{c['text']}\n\n")
                f.write("=" * 80 + "\n\n")

    # -- YouTube clips ------------------------------------------------------
    def search_video_clips(self):
        if not self.youtube:
            self._log("YouTube clips: API not configured (set YOUTUBE_API_KEY) - skipping.")
            return
        all_clips = []
        for query in self.search_queries:
            self._log(f"YouTube clips: '{query}'...")
            try:
                search = self.youtube.search().list(
                    q=query, part="id,snippet", maxResults=10,
                    type="video", relevanceLanguage="en").execute()
                for item in search.get("items", []):
                    vid = item["id"]["videoId"]
                    all_clips.append({
                        "title": item["snippet"]["title"],
                        "url": f"https://youtube.com/watch?v={vid}",
                        "video_id": vid,
                        "description": item["snippet"]["description"],
                        "query": query,
                        "has_transcript": False,
                        "transcript_file": None,
                    })
            except Exception as e:
                self._log(f"YouTube query '{query}' failed: {str(e)[:100]}")
                continue

        # dedupe by video_id
        seen, deduped = set(), []
        for c in all_clips:
            if c["video_id"] not in seen:
                seen.add(c["video_id"])
                deduped.append(c)
        self.results["sources"]["clips"] = deduped
        self._log(f"YouTube: {len(deduped)} unique clips.")

        with open(self.clips_dir / "found_clips.txt", "w", encoding="utf-8") as f:
            for c in deduped:
                f.write(f"TITLE: {c['title']}\n")
                f.write(f"URL: {c['url']}\n")
                f.write(f"QUERY: '{c['query']}'\n")
                f.write(f"DESCRIPTION: {c['description'][:200]}\n")
                f.write("\n" + "-" * 80 + "\n\n")
        with open(self.clips_dir / "transcript_urls.txt", "w", encoding="utf-8") as f:
            for c in deduped:
                f.write(c["url"] + "\n")

    # -- Transcripts --------------------------------------------------------
    def _fetch_one_transcript(self, video_id):
        """Return transcript text for a video, supporting both the 0.7+ instance
        API and the 0.6.x classmethod API. Raises on real failures (no captions)."""
        # 0.7+ : instance .fetch() -> iterable of snippet objects with .text
        try:
            api = YouTubeTranscriptApi()
            fetched = api.fetch(video_id)
            return " ".join(getattr(s, "text", "") for s in fetched).strip()
        except AttributeError:
            pass  # older library shape; fall through to classmethod
        # 0.6.x : classmethod .get_transcript() -> list of dicts with 'text'
        data = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join(d.get("text", "") for d in data).strip()

    def _fetch_one_transcript_ytdlp(self, url):
        """Fallback: pull captions via yt-dlp and strip VTT formatting."""
        opts = {"skip_download": True, "writesubtitles": True,
                "writeautomaticsub": True, "subtitleslangs": ["en"],
                "quiet": True, "no_warnings": True, "subtitlesformat": "vtt"}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        subs = (info.get("subtitles", {}).get("en")
                or info.get("automatic_captions", {}).get("en"))
        if not subs:
            raise RuntimeError("no captions")
        vtt_url = next((s["url"] for s in subs if s.get("ext") == "vtt"), subs[0]["url"])
        raw = requests.get(vtt_url, timeout=15).text
        lines = []
        for ln in raw.splitlines():
            ln = ln.strip()
            if ln and "-->" not in ln and not ln.startswith("WEBVTT") and not ln.isdigit():
                lines.append(re.sub(r"<[^>]+>", "", ln))  # strip inline tags
        return " ".join(lines).strip()

    def fetch_transcripts(self):
        clips = self.results["sources"]["clips"]
        if not clips:
            self._log("Transcripts: no clips yet (run --clips first) - skipping.")
            return
        if not (TRANSCRIPT_API_AVAILABLE or YTDLP_AVAILABLE):
            self._log("Transcripts: neither youtube-transcript-api nor yt-dlp installed - skipping.")
            return

        self._log(f"Transcripts: fetching for {len(clips)} clips...")
        count = 0
        for c in clips:
            text = None
            # primary: youtube-transcript-api
            if TRANSCRIPT_API_AVAILABLE:
                try:
                    text = self._fetch_one_transcript(c["video_id"])
                except Exception:
                    text = None
            # fallback: yt-dlp
            if not text and YTDLP_AVAILABLE:
                try:
                    text = self._fetch_one_transcript_ytdlp(c["url"])
                except Exception:
                    text = None
            if not text:
                self._log(f"  no transcript: {c['title'][:45]}")
                continue

            fname = f"{slugify(c['title'], 50)}_{c['video_id']}.txt"
            with open(self.transcripts_dir / fname, "w", encoding="utf-8") as f:
                f.write(f"VIDEO: {c['title']}\n")
                f.write(f"URL: {c['url']}\n")
                f.write(f"QUERY: '{c['query']}'\n")
                f.write("=" * 80 + "\n\n")
                f.write(text)
            c["has_transcript"] = True
            c["transcript_file"] = fname
            count += 1
            self._log(f"  ok: {c['title'][:50]}")
            time.sleep(1)  # be polite
        self._log(f"Transcripts: {count}/{len(clips)} fetched -> Clips/transcripts/")

    # -- Articles (DuckDuckGo, no API key) ----------------------------------
    def _ddg_search(self, query, max_results=5):
        if not WEB_AVAILABLE:
            return []
        results = []
        try:
            resp = requests.post("https://html.duckduckgo.com/html/",
                                 data={"q": query},
                                 headers={"User-Agent": UA}, timeout=12)
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.select("a.result__a")[:max_results]:
                href = a.get("href", "")
                title = a.get_text(strip=True)
                if "uddg=" in href:  # DDG wraps links in a redirect
                    href = unquote(href.split("uddg=", 1)[1].split("&", 1)[0])
                if href.startswith("http") and title:
                    results.append((title, href))
        except Exception as e:
            self._log(f"  article search failed for '{query}': {str(e)[:80]}")
        return results

    def search_google_articles(self):
        if not WEB_AVAILABLE:
            self._log("Articles: requests/bs4 not installed - skipping.")
            return
        articles, seen = [], set()

        def add(title, url, source_type):
            if url in seen:
                return
            seen.add(url)
            try:
                domain = url.split("/")[2].replace("www.", "")
            except IndexError:
                domain = url
            articles.append({"title": title, "url": url, "source": domain,
                             "type": source_type})

        for query in self.search_queries[:3]:
            self._log(f"Articles: '{query}'...")
            for title, url in self._ddg_search(query, 5):
                add(title, url, "general")
            time.sleep(1)

        for query in self.search_queries[:2]:
            for site in EXPERT_SITES:
                for title, url in self._ddg_search(f"{query} site:{site}", 1):
                    add(title, url, "expert")
                time.sleep(0.5)

        self.results["sources"]["articles"] = articles
        self._log(f"Articles: {len(articles)} found.")

        out = self.research_dir / "articles.txt"
        with open(out, "w", encoding="utf-8") as f:
            for label, kind in (("GENERAL ARTICLES", "general"),
                                ("EXPERT VOCAL PEDAGOGY SITES", "expert")):
                f.write(f"{label}\n" + "=" * 80 + "\n\n")
                for a in [x for x in articles if x["type"] == kind]:
                    f.write(f"TITLE: {a['title']}\n")
                    f.write(f"URL: {a['url']}\n")
                    f.write(f"SOURCE: {a['source']}\n\n")
                    f.write("-" * 80 + "\n\n")

    # -- Google Scholar -----------------------------------------------------
    def search_google_scholar(self):
        if not SCHOLAR_AVAILABLE:
            self._log("Scholar: scholarly not installed - skipping.")
            return
        self._log(f"Scholar: searching for '{self.topic}'...")
        papers = []
        try:
            it = scholarly.search_pubs(f"{self.topic} vocal pedagogy singing")
            for _ in range(10):
                try:
                    p = next(it)
                    bib = p.get("bib", {})
                    papers.append({
                        "title": bib.get("title", "Unknown"),
                        "authors": bib.get("author", []),
                        "year": bib.get("pub_year", "NA"),
                        "citations": int(p.get("num_citations", 0)),
                        "url": p.get("pub_url", ""),
                        "abstract": (bib.get("abstract", "") or "")[:600],
                    })
                except StopIteration:
                    break
                except Exception:
                    continue
        except Exception as e:
            self._log(f"Scholar search failed: {str(e)[:120]}")

        papers.sort(key=lambda p: p["citations"], reverse=True)
        self.results["sources"]["research"] = papers
        self._log(f"Scholar: {len(papers)} papers.")

        out = self.research_dir / "research_papers.txt"
        with open(out, "w", encoding="utf-8") as f:
            for p in papers:
                f.write(f"TITLE: {p['title']}\n")
                f.write(f"AUTHORS: {p['authors']}\n")
                f.write(f"YEAR: {p['year']} | CITATIONS: {p['citations']}\n")
                f.write(f"URL: {p['url']}\n\n")
                f.write(f"ABSTRACT:\n{p['abstract']}\n")
                f.write("\n" + "=" * 80 + "\n\n")

    # -- Report -------------------------------------------------------------
    def generate_report(self):
        self._log("\nWriting evidence_report.md + evidence_data.json ...")
        s = self.results["sources"]
        report = self.base_dir / "evidence_report.md"
        with open(report, "w", encoding="utf-8") as f:
            f.write(f"# Evidence Report - Episode {self.episode_num}: {self.topic}\n\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
            f.write("Queries:\n")
            for q in self.search_queries:
                f.write(f"  - \"{q}\"\n")
            f.write("\n## Counts\n\n")
            f.write(f"- Reddit posts: {len(s['reddit'])}\n")
            f.write(f"- YouTube comments: {len(s['youtube_comments'])}\n")
            f.write(f"- Clips: {len(s['clips'])} "
                    f"({sum(1 for c in s['clips'] if c['has_transcript'])} with transcripts)\n")
            f.write(f"- Articles: {len(s['articles'])}\n")
            f.write(f"- Research papers: {len(s['research'])}\n\n")

            if s["reddit"]:
                f.write("## Top Reddit posts (by upvotes)\n\n")
                for p in s["reddit"][:5]:
                    f.write(f"- **{p['title']}** ({p['score']} upvotes, r/{p['subreddit']})\n")
                    f.write(f"  {p['url']}\n\n")
            if s["youtube_comments"]:
                f.write("## Top YouTube comments (by likes)\n\n")
                for c in s["youtube_comments"][:5]:
                    f.write(f"- **{c['author']}** ({c['likes']} likes): "
                            f"_{c['text'][:140]}..._\n\n")
            if s["research"]:
                f.write("## Top research (by citations)\n\n")
                for p in s["research"][:5]:
                    f.write(f"- **{p['title']}** - {p['year']}, {p['citations']} citations\n\n")

        with open(self.base_dir / "evidence_data.json", "w", encoding="utf-8") as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
        self._log(f"Done. Files in: {self.base_dir}")


def main():
    ap = argparse.ArgumentParser(description="Evidence Aggregator v3.0 - Inside The Voice")
    ap.add_argument("--episode", type=int, required=True)
    ap.add_argument("--topic", required=True,
                    help="breath | high-notes | tension | warmup | any custom topic")
    ap.add_argument("--reddit", action="store_true")
    ap.add_argument("--youtube", action="store_true", help="YouTube comments")
    ap.add_argument("--clips", action="store_true", help="Find videos")
    ap.add_argument("--transcripts", action="store_true", help="Transcripts for found clips")
    ap.add_argument("--articles", action="store_true", help="Web/expert articles")
    ap.add_argument("--scholar", action="store_true", help="Research papers")
    ap.add_argument("--all", action="store_true", help="Run every source")
    args = ap.parse_args()

    flags = {"reddit": args.reddit, "youtube": args.youtube, "clips": args.clips,
             "transcripts": args.transcripts, "articles": args.articles,
             "scholar": args.scholar}
    sources = SOURCE_ORDER if args.all else [k for k, v in flags.items() if v]
    if not sources:
        ap.error("pick at least one source (e.g. --reddit --youtube) or --all")

    print("=" * 70)
    print("EVIDENCE AGGREGATOR v3.0 - Inside The Voice")
    print("=" * 70)
    agg = EvidenceAggregator(args.episode, args.topic)
    agg.run(sources)
    print("\nDONE. Review evidence_report.md, then curate in the web app (python app.py).")


if __name__ == "__main__":
    main()

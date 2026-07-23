# Inside the Voice — Evidence Aggregator

A personal, local, **read-only** research tool. It gathers public evidence for
episodes of the *Inside the Voice* YouTube show (analysis/commentary on singing
and vocal technique): what real people ask, what coaches teach, and what research
says — so each episode's argument is grounded in evidence.

**Read-only.** It never posts, comments, votes, messages, or moderates. It only
reads public content through official APIs.

## Sources (each fails gracefully if unconfigured)
- **Reddit** (praw) — public posts + top comments from vocal subreddits
- **YouTube** (Data API) — comments and video clips
- **Transcripts** (youtube-transcript-api, yt-dlp fallback) — for found clips
- **Articles** (DuckDuckGo) — no key needed
- **Research papers** (Google Scholar via `scholarly`) — no key needed

## Use
    pip install -r requirements.txt
    # set API keys as environment variables (see SETUP.md)
    python app.py     # local web app at http://127.0.0.1:5000
    # or, command line:
    python evidence_aggregator.py --episode 1 --topic warmup --all

The web app runs a gather, then lets you tag each piece of evidence to one of
three claims (problem exists / belief is incomplete / the corrected version) and
export a curated markdown file.

See **SETUP.md** for full setup and how to obtain the API keys.

## Notes
Single-user, personal, low-volume. Runs locally — not a hosted service.
API keys are read from environment variables only; nothing is hardcoded.

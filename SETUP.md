# Evidence Aggregator v3.0 — Setup

Personal, local tool. Runs on your Windows machine. Two ways to use it:

- **Web app** (recommended): `python app.py` → open `http://127.0.0.1:5000`
- **Command line**: `python evidence_aggregator.py --episode 1 --topic warmup --all`

---

## 1. Install dependencies

From the `Evidence Aggregator` folder, in CMD:

```
pip install -r requirements.txt
```

That installs everything, including `flask` (web app), `praw` (Reddit),
`yt-dlp` (transcript fallback), and `youtube-transcript-api`.

## 2. Set your API keys (environment variables)

The tool reads keys from environment variables — nothing is hardcoded.
Create a `set_keys.bat` in this folder (it is git-ignored / keep it private):

```bat
set YOUTUBE_API_KEY=your_youtube_key_here
set REDDIT_CLIENT_ID=your_reddit_client_id
set REDDIT_CLIENT_SECRET=your_reddit_client_secret
set REDDIT_USER_AGENT=inside-the-voice by u/your_reddit_username
```

Run `set_keys.bat` once per CMD session **before** `app.py` or the CLI.

> ⚠️ **Rotate your old YouTube key.** The previous `set_keys.bat` had a key
> committed in plaintext. Treat it as compromised: create a new key in Google
> Cloud Console and delete the old one.

### How to get the keys

**YouTube Data API v3** (for comments + clips)
1. console.cloud.google.com → create/select a project.
2. "APIs & Services" → Enable APIs → enable **YouTube Data API v3**.
3. Credentials → Create credentials → **API key**. Copy it.

**Reddit** (for the Reddit source — the new part)
1. reddit.com/prefs/apps → **Create another app…**
2. Choose type **"script"**. Name it anything. Redirect URI: `http://localhost:8080`.
3. After creating: the string under the app name is your **client_id**;
   the "secret" field is your **client_secret**.
4. `REDDIT_USER_AGENT` can be any short descriptive string with your username.

Reddit read-only script auth needs **no** Reddit password for public search.

`articles` (DuckDuckGo) and `scholar` need **no** keys.

## 3. Run it

**Web app:**
```
set_keys.bat
python app.py
```
Open `http://127.0.0.1:5000`. Pick episode + topic + sources → **Gather** →
watch the log → open the episode → tag each item to Claim 1/2/3 or Cut →
**Export curated .md**.

**CLI:**
```
set_keys.bat
python evidence_aggregator.py --episode 1 --topic warmup --reddit --youtube --clips --transcripts --articles --scholar
```
(or `--all`). Output lands in `episodes/Episode_01_warmup/`.

## Sources & what feeds which claim

| Source        | Needs key | Feeds |
|---------------|-----------|-------|
| `reddit`      | Reddit    | Claim 1 (problem exists) |
| `youtube`     | YouTube   | Claim 1 |
| `clips`       | YouTube   | Claims 2 & 3 (coach advice) |
| `transcripts` | —         | Claims 2 & 3 (runs after clips) |
| `articles`    | —         | Claims 2 & 3 |
| `scholar`     | —         | Claims 2 & 3 (research) |

Every source fails soft — a missing key or a dead source logs a line and the
run continues with the others.

## Topics

Built-in (7 queries each): `breath`, `high-notes`, `tension`, `warmup`.
Any other topic works too — either add it to `TOPIC_QUERIES` in
`evidence_aggregator.py`, or type custom queries in the web app's query box.

## Files produced (per episode)

```
episodes/Episode_01_warmup/
├── Evidence/reddit.txt, youtube_comments.txt
├── Clips/found_clips.txt, transcript_urls.txt, transcripts/*.txt
├── Research/articles.txt, research_papers.txt
├── evidence_report.md      # human summary + counts
├── evidence_data.json      # structured data (the web app reads this)
├── curation.json           # your Claim 1/2/3/Cut tags (web app writes this)
└── curated_evidence.md     # exported, grouped by claim
```

## Notes / limits

- Personal low-volume use. The free transcript libraries work from your home IP;
  they get blocked from cloud/datacenter IPs, so don't move this to a server.
- The old three scripts are kept in `_archive/` — nothing was deleted.

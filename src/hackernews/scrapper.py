import argparse
import html
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUT = PROJECT_ROOT / "data" / "raw" / "hackernews" / "jobs.json"

ALGOLIA_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
ALGOLIA_ITEM_URL = "https://hn.algolia.com/api/v1/items/{item_id}"

HEADERS = {"User-Agent": "job-fraud-research-scraper/1.0 (academic project)"}

TAG_RE = re.compile(r"<[^>]+>")
HREF_RE = re.compile(r'href="([^"]+)"')
EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

# Known URL shorteners -- shortened links hide the real destination, which is
# itself a mild red flag in job postings (legit company postings usually link
# straight to their own domain).
URL_SHORTENER_DOMAINS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly",
    "rebrand.ly", "shorturl.at", "cutt.ly", "tiny.cc", "rb.gy",
}

FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
    "icloud.com", "protonmail.com", "mail.com", "yandex.com", "gmx.com",
}

ATS_DOMAINS = {
    "greenhouse.io", "lever.co", "workday.com", "myworkdayjobs.com",
    "indeed.com", "linkedin.com", "ashbyhq.com", "smartrecruiters.com",
    "bamboohr.com", "breezy.hr", "jobvite.com",
}

def get_domain(url):
    """Extract a lowercased registrable-ish domain (netloc, no port/www)
    from a URL. Returns None if it can't be parsed."""
    try:
        netloc = urlparse(url).netloc.lower()
    except ValueError:
        return None
    if not netloc:
        return None
    if netloc.startswith("www."):
        netloc = netloc[4:]
    netloc = netloc.split(":")[0]  # drop port if present
    return netloc or None


def extract_urls(raw_html):
    """Pull out actual link targets before we strip HTML tags, so we don't
    silently lose them (link destinations -- mismatched domains, shorteners,
    etc. -- are a real fraud signal)."""
    if not raw_html:
        return []
    urls = HREF_RE.findall(raw_html)
    # de-dupe while preserving order
    seen = set()
    deduped = []
    for u in urls:
        unescaped = html.unescape(u)
        if unescaped not in seen:
            seen.add(unescaped)
            deduped.append(unescaped)
    return deduped


def extract_emails(clean_text):
    """Pull plain-text email addresses out of the cleaned comment text."""
    if not clean_text:
        return []
    seen = set()
    deduped = []
    for e in EMAIL_RE.findall(clean_text):
        if e not in seen:
            seen.add(e)
            deduped.append(e)
    return deduped


def analyze_links(urls, emails):
    """Derive domain-level fields and heuristic red-flag booleans from raw
    urls/emails. These are cheap, explainable features worth having at scrape
    time rather than re-deriving later."""
    url_domains = []
    for u in urls:
        d = get_domain(u)
        if d and d not in url_domains:
            url_domains.append(d)

    email_domains = []
    for e in emails:
        if "@" in e:
            d = e.split("@", 1)[1].lower()
            if d not in email_domains:
                email_domains.append(d)

    has_url_shortener = any(d in URL_SHORTENER_DOMAINS for d in url_domains)
    uses_free_email_provider = any(d in FREE_EMAIL_DOMAINS for d in email_domains)
    links_to_known_ats = any(
        any(d == ats or d.endswith("." + ats) for ats in ATS_DOMAINS)
        for d in url_domains
    )

    return {
        "url_domains": url_domains,
        "email_domains": email_domains,
        "has_url_shortener": has_url_shortener,
        "uses_free_email_provider": uses_free_email_provider,
        "links_to_known_ats": links_to_known_ats,
    }


def clean_html_text(raw):
    if not raw:
        return ""
    text = html.unescape(raw)
    text = TAG_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def find_whoishiring_stories(start_year, end_year, session, pause=0.3):
    """
    Find all 'Ask HN: Who is hiring?' story ids/titles within the year range,
    via Algolia search filtered to author=whoishiring and tag=story.
    """
    stories = []
    page = 0
    while True:
        params = {
            "query": "Who is hiring",
            "tags": "story,author_whoishiring",
            "hitsPerPage": 100,
            "page": page,
        }
        resp = session.get(ALGOLIA_SEARCH_URL, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        hits = data.get("hits", [])
        if not hits:
            break

        for hit in hits:
            title = hit.get("title") or ""
            if "who is hiring" not in title.lower():
                continue
            created = hit.get("created_at", "")
            try:
                year = datetime.fromisoformat(created.replace("Z", "+00:00")).year
            except ValueError:
                continue
            if start_year <= year <= end_year:
                stories.append(
                    {
                        "story_id": hit.get("objectID"),
                        "title": title,
                        "created_at": created,
                    }
                )

        page += 1
        if page >= data.get("nbPages", 0):
            break
        time.sleep(pause)

    return stories


def fetch_top_level_postings(story_id, session, pause=0.3):
    """
    Fetch a story's full comment tree via the items endpoint and return
    only top-level comments (direct children of the story) as postings.
    """
    url = ALGOLIA_ITEM_URL.format(item_id=story_id)
    resp = session.get(url, headers=HEADERS, timeout=30)
    if resp.status_code != 200:
        return []
    data = resp.json()
    children = data.get("children", []) or []

    postings = []
    for child in children:
        if child.get("type") != "comment":
            continue
        raw_text = child.get("text") or ""
        clean = clean_html_text(raw_text)
        if len(clean) < 40:
            # skip near-empty / deleted / "[flagged]" comments
            continue
        urls = extract_urls(raw_text)
        emails = extract_emails(clean)
        link_info = analyze_links(urls, emails)
        posting = {
            "comment_id": child.get("id"),
            "author": child.get("author"),
            "created_at": child.get("created_at"),
            "text_raw": raw_text,
            "text_clean": clean,
            "urls": urls,
            "emails": emails,
        }
        posting.update(link_info)
        postings.append(posting)

    time.sleep(pause)
    return postings


def main():
    parser = argparse.ArgumentParser(description="Scrape HN Who is Hiring postings")
    parser.add_argument("--start-year", type=int, default=2023)
    parser.add_argument("--end-year", type=int, default=datetime.now().year)
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help=f"Output JSON file path (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--max-stories",
        type=int,
        default=None,
        help="Limit number of monthly threads processed (useful for testing)",
    )
    args = parser.parse_args()

    session = requests.Session()

    print(f"Searching for Who is Hiring threads {args.start_year}-{args.end_year}...", file=sys.stderr)
    stories = find_whoishiring_stories(args.start_year, args.end_year, session)
    print(f"Found {len(stories)} monthly threads.", file=sys.stderr)

    if args.max_stories:
        stories = stories[: args.max_stories]

    all_records = []
    for i, story in enumerate(stories, 1):
        print(
            f"[{i}/{len(stories)}] {story['title']} (id={story['story_id']})",
            file=sys.stderr,
        )
        try:
            postings = fetch_top_level_postings(story["story_id"], session)
        except requests.RequestException as e:
            print(f"  ERROR fetching story {story['story_id']}: {e}", file=sys.stderr)
            continue

        for p in postings:
            record = {
                "story_id": story["story_id"],
                "story_title": story["title"],
                "story_month": story["created_at"][:7],  # YYYY-MM
                "comment_id": p["comment_id"],
                "author": p["author"],
                "created_at": p["created_at"],
                "text_raw": p["text_raw"],
                "text_clean": p["text_clean"],
                "urls": p["urls"],
                "emails": p["emails"],
                "url_domains": p["url_domains"],
                "email_domains": p["email_domains"],
                "has_url_shortener": p["has_url_shortener"],
                "uses_free_email_provider": p["uses_free_email_provider"],
                "links_to_known_ats": p["links_to_known_ats"],
                "source": "hackernews_whoishiring",
                "structure_type": "unstructured_freetext",
                "label": "unlabeled",  # fill in during annotation phase
            }
            all_records.append(record)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)

    print(f"Done. Wrote {len(all_records)} postings to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()

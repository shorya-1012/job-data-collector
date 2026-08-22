import argparse
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import serpapi
from dotenv import load_dotenv


SEARCH_TERMS = [
    "Software Engineer",
    "Marketing",
    "Sales",
    "Business Development",
    "Operations",
    "Human Resources",
    "Finance",
    "Customer Support",
    "Product Manager",
    "Design",
]

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

OUTPUT_PATH = (
    REPO_ROOT
    / "data"
    / "processed"
    / "lever"
    / "company_tokens.json"
)

ENV_PATH = REPO_ROOT / ".env"
load_dotenv(ENV_PATH)

TOKEN_RE = re.compile(
    r"^/([A-Za-z0-9._-]+)/",
    re.IGNORECASE,
)

TOKEN_BLOCKLIST = {
    "jobs",
    "embed",
}

def build_query(term: str) -> str:
    return f'site:jobs.lever.co "{term}"'

def extract_token(url: str) -> str | None:
    try:
        parsed = urlparse(url)
        if parsed.netloc.lower() != "jobs.lever.co":
            return None

        match = TOKEN_RE.match(parsed.path)

        if not match:
            return None

        token = match.group(1).lower()
        if token in TOKEN_BLOCKLIST:
            return None

        return token
    except Exception:
        return None

def search(
    client: serpapi.Client,
    term: str,
    page: int,
) -> dict:
    params = {
        "engine": "google",
        "q": build_query(term),
        "start": page * 10,
    }

    return client.search(params)


def find_tokens(
    client: serpapi.Client,
    pages_per_term: int,
) -> dict:
    results: dict[str, dict] = {}

    for term in SEARCH_TERMS:
        print(f"[*] Searching: {build_query(term)}")

        for page in range(pages_per_term):
            try:
                data = search(
                    client,
                    term,
                    page,
                )

            except serpapi.HTTPError as e:
                print(
                    f"  [!] SerpApi HTTP error "
                    f"for '{term}' page {page}: {e}"
                )
                break

            except serpapi.TimeoutError as e:
                print(
                    f"  [!] SerpApi timeout "
                    f"for '{term}' page {page}: {e}"
                )
                break

            organic_results = data.get(
                "organic_results",
                [],
            )

            if not organic_results:
                print(
                    f"    page {page}: no results"
                )
                break

            page_tokens = set()

            for result in organic_results:
                url = result.get("link")

                if not url:
                    continue

                token = extract_token(url)

                if not token:
                    continue

                page_tokens.add(token)

                entry = results.setdefault(
                    token,
                    {
                        "queries_found_in": [],
                        "sample_urls": [],
                    },
                )

                if term not in entry["queries_found_in"]:
                    entry["queries_found_in"].append(term)

                if (
                    url not in entry["sample_urls"]
                    and len(entry["sample_urls"]) < 5
                ):
                    entry["sample_urls"].append(url)

            print(
                f"    page {page}: "
                f"{len(page_tokens)} unique tokens"
            )

    return results


def save_results(
    results: dict,
    path: Path = OUTPUT_PATH,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    existing = {}

    if path.exists():
        try:
            existing = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

        except json.JSONDecodeError:
            print(
                "[!] Existing JSON is invalid; "
                "starting fresh."
            )

    for token, data in results.items():
        if token in existing:
            existing[token]["queries_found_in"] = sorted(
                set(
                    existing[token].get(
                        "queries_found_in",
                        [],
                    )
                )
                | set(
                    data["queries_found_in"]
                )
            )

            merged_urls = (
                existing[token].get(
                    "sample_urls",
                    [],
                )
                + data["sample_urls"]
            )

            existing[token]["sample_urls"] = list(
                dict.fromkeys(merged_urls)
            )[:5]

        else:
            existing[token] = data

    path.write_text(
        json.dumps(
            existing,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        f"\n[+] Saved "
        f"{len(existing)} total tokens -> {path}"
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Find Lever company tokens "
            "using SerpApi."
        )
    )

    parser.add_argument(
        "--pages",
        type=int,
        default=1,
        help=(
            "Pages of Google results per search "
            "term (default: 1)"
        ),
    )

    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Override output path",
    )

    args = parser.parse_args()

    api_key = os.getenv("SERPAPI_KEY")

    if not api_key:
        raise SystemExit(
            f"SERPAPI_KEY not found.\n"
            f"Create {ENV_PATH} with:\n\n"
            f"SERPAPI_KEY=your-key"
        )

    client = serpapi.Client(
        api_key=api_key
    )

    results = find_tokens(
        client,
        pages_per_term=args.pages,
    )

    output_path = (
        Path(args.output)
        if args.output
        else OUTPUT_PATH
    )

    save_results(
        results,
        output_path,
    )

    print("\nTokens found this run:")

    for token in sorted(results):
        queries = ", ".join(
            results[token]["queries_found_in"]
        )

        print(
            f"  - {token} ({queries})"
        )


if __name__ == "__main__":
    main()

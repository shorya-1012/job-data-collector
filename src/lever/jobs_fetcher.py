import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

REPO_ROOT = (
    Path(__file__).resolve().parent.parent.parent
)

DEFAULT_INPUT = (
    REPO_ROOT
    / "data"
    / "processed"
    / "lever"
    / "company_tokens.json"
)

DEFAULT_OUTPUT = (
    REPO_ROOT
    / "data"
    / "raw"
    / "lever"
    / "jobs.json"
)

API_URL = (
    "https://api.lever.co/v0/postings"
)

session = requests.Session()

session.headers.update(
    {
        "User-Agent": (
            "FakeJobResearch/1.0 "
            "(academic dataset collection)"
        ),
        "Accept": "application/json",
    }
)


def current_time() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def html_to_text(
    html: str | None,
) -> str:
    if not html:
        return ""

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    return soup.get_text(
        "\n",
        strip=True,
    )


def load_tokens(
    path: Path,
) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"Token file does not exist: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            "company_tokens.json must contain "
            "a JSON object."
        )

    return data

def load_existing_jobs(
    path: Path,
) -> list[dict]:

    if not path.exists():
        return []

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

    except json.JSONDecodeError:
        print(
            "[!] Existing jobs.json is invalid."
        )
        print(
            "[!] Starting with an empty dataset."
        )
        return []

    if not isinstance(data, list):
        raise ValueError(
            "jobs.json must contain a JSON array."
        )

    return data

def fetch_board(
    token: str,
) -> requests.Response:
    url = f"{API_URL}/{token}"

    return session.get(
        url,
        params={
            "mode": "json",
        },
        timeout=30,
    )

def normalize_job(
    job: dict,
    token: str,
    token_data: dict,
) -> dict:
    """
    Convert a Lever public posting into the
    normalized structure used by our dataset.
    """

    categories = (
        job.get("categories")
        or {}
    )

    description_html = (
        job.get("description")
        or ""
    )

    description_text = (
        job.get("descriptionPlain")
        or html_to_text(
            description_html
        )
    )

    location = categories.get(
        "location"
    )

    all_locations = categories.get(
        "allLocations",
        [],
    )

    if all_locations:
        location_name = ", ".join(
            str(location)
            for location in all_locations
            if location
        )
    else:
        location_name = location

    urls = (
        job.get("urls")
        or {}
    )

    return {
        "source": "lever",

        "board_token": token,

        "company": token_data.get(
            "company",
            token,
        ),

        "job_id": job.get(
            "id"
        ),

        "internal_job_id": None,

        "title": job.get(
            "text"
        ),

        "location": {
            "name": location_name
        },

        "description_html": (
            description_html
        ),

        "description_text": (
            description_text
        ),

        "job_url": (
            urls.get("show")
            or job.get("hostedUrl")
        ),

        "updated_at": (
            datetime.fromtimestamp(
                job["updatedAt"] / 1000,
                timezone.utc,
            ).isoformat()
            if job.get("updatedAt")
            else None
        ),

        "departments": (
            [
                {
                    "name": categories.get(
                        "department"
                    )
                }
            ]
            if categories.get(
                "department"
            )
            else []
        ),

        "offices": [],

        "metadata": {
            "team": categories.get(
                "team"
            ),
            "commitment": categories.get(
                "commitment"
            ),
            "level": categories.get(
                "level"
            ),
            "workplace_type": job.get(
                "workplaceType"
            ),
            "state": job.get(
                "state"
            ),
            "tags": job.get(
                "tags",
                [],
            ),
            "salary_description": job.get(
                "salaryDescription"
            ),
            "salary_range": job.get(
                "salaryRange"
            ),
            "requisition_codes": job.get(
                "requisitionCodes",
                [],
            ),
        },

        "discovery": {
            "queries_found_in": token_data.get(
                "queries_found_in",
                [],
            ),

            "sample_urls": token_data.get(
                "sample_urls",
                [],
            ),
        },

        "scraped_at": current_time(),
    }

def scrape(
    tokens: dict,
    existing_jobs: list[dict],
    delay: float,
) -> list[dict]:
    """
    Fetch every Lever board and return the
    complete deduplicated job list.
    """

    jobs_by_key: dict[
        tuple[str, str],
        dict,
    ] = {}

    for job in existing_jobs:

        token = job.get(
            "board_token"
        )

        job_id = job.get(
            "job_id"
        )

        if token is None or job_id is None:
            continue

        key = (
            token,
            str(job_id),
        )

        jobs_by_key[key] = job

    total_tokens = len(tokens)

    print(
        f"[*] Boards to fetch: {total_tokens}"
    )

    print(
        f"[*] Existing jobs: "
        f"{len(jobs_by_key)}"
    )

    print()

    for index, (
        token,
        token_data,
    ) in enumerate(
        tokens.items(),
        start=1,
    ):

        print(
            f"[{index}/{total_tokens}] "
            f"{token}"
        )

        try:

            response = fetch_board(
                token
            )

            print(
                f"    HTTP {response.status_code}"
            )

            if response.status_code == 404:

                print(
                    "    [!] Board not found"
                )

                continue

            if response.status_code == 429:

                print(
                    "    [!] Rate limited"
                )

                retry_after = (
                    response.headers.get(
                        "Retry-After"
                    )
                )

                if retry_after:
                    print(
                        f"    Retry-After: "
                        f"{retry_after}"
                    )

                print(
                    "    Stopping fetcher."
                )

                break

            response.raise_for_status()

            data = response.json()

            # Lever's public v0 postings endpoint
            # returns the postings as a JSON array.
            if not isinstance(data, list):
                print(
                    "    [!] Unexpected response "
                    "format: expected a list."
                )
                continue

            jobs = data

            print(
                f"    Jobs found: "
                f"{len(jobs)}"
            )

            for job in jobs:

                job_id = job.get(
                    "id"
                )

                if job_id is None:
                    continue

                key = (
                    token,
                    str(job_id),
                )

                normalized = normalize_job(
                    job,
                    token,
                    token_data,
                )

                jobs_by_key[key] = normalized

        except requests.RequestException as error:

            print(
                f"    [!] Request failed: "
                f"{error}"
            )

        except json.JSONDecodeError:

            print(
                "    [!] Lever returned "
                "invalid JSON."
            )

        except Exception as error:

            print(
                f"    [!] Unexpected error: "
                f"{error}"
            )

        time.sleep(delay)

    return list(
        jobs_by_key.values()
    )


def save_jobs(
    jobs: list[dict],
    path: Path,
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Sort for deterministic output.
    jobs.sort(
        key=lambda job: (
            str(
                job.get(
                    "board_token",
                    "",
                )
            ),
            str(
                job.get(
                    "job_id",
                    "",
                )
            ),
        )
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            jobs,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print(
        f"[+] Saved {len(jobs)} jobs"
    )

    print(
        f"[+] Output: {path}"
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Fetch Lever jobs using "
            "company board tokens."
        )
    )

    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help=(
            "Path to company_tokens.json "
            "(default: "
            "data/processed/lever/"
            "company_tokens.json)"
        ),
    )

    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help=(
            "Path to jobs.json "
            "(default: "
            "data/raw/lever/jobs.json)"
        ),
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help=(
            "Delay between board requests "
            "(default: 1 second)"
        ),
    )

    args = parser.parse_args()

    input_path = (
        Path(args.input)
        if args.input
        else DEFAULT_INPUT
    )

    output_path = (
        Path(args.output)
        if args.output
        else DEFAULT_OUTPUT
    )

    print(
        "[*] Loading tokens from:"
    )

    print(
        f"    {input_path}"
    )

    tokens = load_tokens(
        input_path
    )

    print(
        f"[*] Found {len(tokens)} "
        f"Lever boards"
    )

    existing_jobs = load_existing_jobs(
        output_path
    )

    jobs = scrape(
        tokens=tokens,
        existing_jobs=existing_jobs,
        delay=args.delay,
    )

    save_jobs(
        jobs,
        output_path,
    )


if __name__ == "__main__":
    main()

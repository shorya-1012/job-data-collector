import json
from pathlib import Path

INPUT_FILE = Path("data/raw/greenhouse/jobs.json")
OUTPUT_FILE = Path("data/processed/greenhouse/jobs.json")

def main():
    # Load raw jobs
    with INPUT_FILE.open("r", encoding="utf-8") as f:
        jobs = json.load(f)

    print(f"Loaded {len(jobs):,} jobs")

    seen = set()
    unique_jobs = []
    duplicate_count = 0
    invalid_count = 0

    for job in jobs:
        board_token = job.get("board_token")
        job_id = job.get("job_id")

        # Skip jobs that don't have the fields required for deduplication
        if board_token is None or job_id is None:
            invalid_count += 1
            unique_jobs.append(job)
            continue

        key = (board_token, job_id)

        if key in seen:
            duplicate_count += 1
            continue

        seen.add(key)
        unique_jobs.append(job)

    # Create output directory
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Write deduplicated dataset
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(
            unique_jobs,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print("Deduplication complete")
    print("----------------------")
    print(f"Original jobs : {len(jobs):,}")
    print(f"Unique jobs   : {len(unique_jobs):,}")
    print(f"Duplicates    : {duplicate_count:,}")
    print(f"Invalid jobs  : {invalid_count:,}")
    print()
    print(f"Input         : {INPUT_FILE}")
    print(f"Output        : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

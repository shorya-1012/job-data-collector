import json
from pathlib import Path


DATA_DIR = Path("data/processed")

def count_jobs(path: Path) -> int:
    """Count records in a jobs.json file."""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            return len(data)

        if isinstance(data, dict):
            return len(data)

        return 0

    except (json.JSONDecodeError, OSError) as e:
        print(f"Error reading {path}: {e}")
        return 0


def main():
    if not DATA_DIR.exists():
        print(f"Directory not found: {DATA_DIR}")
        return

    totals = {}
    final_total = 0

    # Find data/processed/<source>/jobs.json
    for jobs_file in DATA_DIR.glob("*/jobs.json"):
        source = jobs_file.parent.name
        count = count_jobs(jobs_file)

        totals[source] = count
        final_total += count

    print("\nProcessed Job Data")
    print("=" * 40)

    for source, count in sorted(totals.items()):
        print(f"{source:<20} {count:>10,}")

    print("-" * 40)
    print(f"{'TOTAL FINAL RECORDS':<20} {final_total:>10,}")
    print("=" * 40)


if __name__ == "__main__":
    main()

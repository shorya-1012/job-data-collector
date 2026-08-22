import json
from pathlib import Path

DATA_DIR = Path("data/processed")

def format_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]

    value = float(size)

    for unit in units:
        if value < 1024:
            return f"{value:.2f} {unit}"

        value /= 1024

    return f"{value:.2f} PB"


def count_json_records(path: Path) -> int:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, list):
        return len(data)

    if isinstance(data, dict):
        return 1

    return 0


def count_jsonl_records(path: Path) -> int:
    count = 0

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                count += 1

    return count


def count_records(path: Path) -> int:
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        return count_jsonl_records(path)

    if path.suffix.lower() == ".json":
        return count_json_records(path)

    return 0


def print_file_stats(path: Path, base_dir: Path) -> tuple[int, int]:
    size = path.stat().st_size
    records = count_records(path)

    relative_path = path.relative_to(base_dir)

    print(f"  {relative_path}")
    print(f"    Records:   {records:,}")
    print(f"    Size:      {format_size(size)}")
    print()

    return records, size


def main() -> None:
    if not DATA_DIR.exists():
        print(f"Error: {DATA_DIR} does not exist.")
        return

    files = sorted(
        path
        for path in DATA_DIR.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".json", ".jsonl", ".ndjson"}
    )

    if not files:
        print(f"No dataset files found in {DATA_DIR}")
        return

    total_records = 0
    total_size = 0

    print("=" * 60)
    print("                 DATASET STATISTICS")
    print("=" * 60)
    print()

    # Group files by their immediate parent directory.
    sources: dict[str, list[Path]] = {}

    for path in files:
        relative = path.relative_to(DATA_DIR)

        if len(relative.parts) > 1:
            source = relative.parts[0]
        else:
            source = "root"

        sources.setdefault(source, []).append(path)

    for source, source_files in sources.items():
        print(f"{source.upper()}")
        print("-" * 60)

        source_records = 0
        source_size = 0

        for path in source_files:
            records, size = print_file_stats(path, DATA_DIR)

            source_records += records
            source_size += size

        print(f"  {source} total:")
        print(f"    Records:   {source_records:,}")
        print(f"    Size:      {format_size(source_size)}")
        print()

        total_records += source_records
        total_size += source_size

    print("=" * 60)
    print("TOTAL")
    print("-" * 60)
    print(f"  Records:   {total_records:,}")
    print(f"  Size:      {format_size(total_size)}")
    print("=" * 60)


if __name__ == "__main__":
    main()

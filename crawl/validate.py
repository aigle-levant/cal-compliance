import json
import re
from collections import Counter
from pathlib import Path

INPUT = "../data/extract.jsonl"

# Escaped the asterisks (\*) to safely detect optional markdown bolding tags
SECTION_RE = re.compile(
    r"§\s*\*{0,2}\s*(\d+(?:\.\d+)*)",
    re.IGNORECASE,
)

TITLE_RE = re.compile(
    r"§\s*\*{0,2}\s*(\d+(?:\.\d+)).?\s(.+?)$",
    re.MULTILINE,
)

HISTORY_PATTERNS = [
    "register",
    "operative",
    "amendment filed",
    "editorial correction",
    "repealer",
    "certificate of compliance",
]

def clean_text(text: str) -> str:
    return text.replace("**", "")

def extract_section(text: str):
    text = clean_text(text)
    m = SECTION_RE.search(text)
    if not m:
        return None
    return m.group(1)

def is_history_chunk(text: str) -> bool:
    text = text.lower()
    hits = sum(
        1
        for pattern in HISTORY_PATTERNS
        if pattern in text
    )
    return hits >= 3

def main():
    stats = Counter()
    mismatches = []
    
    input_path = Path(INPUT)
    if not input_path.exists():
        print(f"Error: Target file '{INPUT}' not found.")
        return

    print("Running segment validation checks...")
    with open(input_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            if not line.strip():
                continue
                
            row = json.loads(line)
            # Support reading either "text" field or "content_markdown" field
            text = row.get("text") or row.get("content_markdown") or ""
            metadata_section = row.get("section_number")

            actual_section = extract_section(text)

            if not actual_section:
                stats["unknown"] += 1
                mismatches.append(
                    {
                        "line": line_num,
                        "id": row.get("chunk_id") or row.get("id"),
                        "reason": "section_not_found",
                        "metadata_section": metadata_section,
                    }
                )
                continue

            if str(metadata_section) != str(actual_section):
                stats["mismatch"] += 1
                mismatches.append(
                    {
                        "line": line_num,
                        "id": row.get("chunk_id") or row.get("id"),
                        "reason": "section_mismatch",
                        "metadata_section": metadata_section,
                        "actual_section": actual_section,
                    }
                )
            else:
                stats["matched"] += 1

            if is_history_chunk(text):
                stats["history_chunks"] += 1

    total = stats["matched"] + stats["mismatch"] + stats["unknown"]
    
    print("\n=== VALIDATION REPORT ===")
    print(f"TOTAL LINES RESCANURRED : {total}")
    print(f"MATCHED METADATA        : {stats['matched']}")
    print(f"MISMATCHED SECTIONS     : {stats['mismatch']}")
    print(f"COULD NOT EXTRACT       : {stats['unknown']}")
    print(f"REULATORY HISTORY CHUNKS: {stats['history_chunks']}")
    
    output_report = Path("validation_report.json")
    output_report.write_text(
        json.dumps(mismatches, indent=2),
        encoding="utf-8",
    )
    print(f"\nSaved validation discrepancies log to {output_report}")

if __name__ == "__main__":
    main()
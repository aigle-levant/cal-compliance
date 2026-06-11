import json
from pathlib import Path

URLS_FILE = "../data/urls.jsonl"
EXTRACT_FILE = "../data/extract.jsonl"
LOG_FILE = "../data/log.jsonl"
REPORT_FILE = "../data/coverage.json"

def count_discovered_urls():
    urls = set()
    if not Path(URLS_FILE).exists():
        return urls

    with open(URLS_FILE, "r", encoding="utf8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                urls.add(json.loads(line)["url"])
            except Exception:
                pass

    return urls

def analyze_extractions():
    stats = {
        "records": 0,
        "missing_title_number": 0,
        "missing_section_number": 0,
        "missing_heading": 0,
        "empty_content": 0,
    }

    if not Path(EXTRACT_FILE).exists():
        return stats

    with open(EXTRACT_FILE, "r", encoding="utf8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                stats["records"] += 1

                if not record.get("title_number"):
                    stats["missing_title_number"] += 1

                if not record.get("section_number"):
                    stats["missing_section_number"] += 1

                if not record.get("section_heading"):
                    stats["missing_heading"] += 1

                content = record.get("content_markdown", "").strip()
                if len(content) < 100:
                    stats["empty_content"] += 1
            except Exception:
                pass

    return stats

def analyze_logs():
    success = 0
    failed = 0
    skipped = 0

    if not Path(LOG_FILE).exists():
        return {
            "success": 0,
            "failed": 0,
            "skipped": 0
        }

    with open(LOG_FILE, "r", encoding="utf8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                log = json.loads(line)
                status = log.get("status")

                if status == "success":
                    success += 1
                elif status == "failed":
                    failed += 1
                elif status == "skipped":
                    skipped += 1
            except Exception:
                pass

    return {
        "success": success,
        "failed": failed,
        "skipped": skipped
    }

def main():
    discovered = count_discovered_urls()
    extraction_stats = analyze_extractions()
    log_stats = analyze_logs()

    coverage_percent = 0
    if len(discovered) > 0:
        coverage_percent = round((log_stats["success"] / len(discovered)) * 100, 2)

    report = {
        "summary": {
            "total_discovered_urls": len(discovered),
            "successful_extractions": log_stats["success"],
            "failed_extractions": log_stats["failed"],
            "skipped_pages": log_stats["skipped"],
            "coverage_percent": coverage_percent
        },
        "data_quality": {
            "total_records": extraction_stats["records"],
            "missing_title_number": extraction_stats["missing_title_number"],
            "missing_section_number": extraction_stats["missing_section_number"],
            "missing_heading": extraction_stats["missing_heading"],
            "empty_content": extraction_stats["empty_content"]
        }
    }

    with open(REPORT_FILE, "w", encoding="utf8") as f:
        json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))
    print(f"\nCoverage report saved to: {REPORT_FILE}")

if __name__ == "__main__":
    main()
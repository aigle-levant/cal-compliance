from collections import defaultdict
import json

groups = defaultdict(list)

with open("../data/chunks.jsonl", encoding="utf8") as f:
    for line in f:
        row = json.loads(line)
        groups[row["chunk_id"]].append(row)

for cid, rows in groups.items():
    texts = {r["text"][:200] for r in rows}

    if len(texts) > 1:
        print("\n", cid)

        for r in rows:
            print("URL:", r["source_url"])
            print("TITLE:", r.get("section_title"))
            print()
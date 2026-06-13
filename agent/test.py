import json
import time
from pathlib import Path
from config import (
    get_supabase,
)

CHUNKS_FILE = Path("../data/chunks.jsonl")
TABLE_NAME = "compliance_data"
BATCH_SIZE = 25
supabase = get_supabase()

result = (
    supabase.table("compliance_data")
    .select("id", count="exact")
    .execute()
)

print(result.count)
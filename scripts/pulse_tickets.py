#!/usr/bin/env python3
"""
pulse_tickets.py
Append a minimal Catalyst tickets signal snapshot to signals/tickets.json
so The Signal can read a rolling history instead of a single "latest".

Example:
  python scripts/pulse_tickets.py \
    --in seeds/tickets.yml \
    --out signals/tickets.json \
    --name "FourTwenty • The Catalyst" \
    --module "catalyst-model" \
    --emoji "⚙️" \
    --url "https://zbreeden.github.io/catalyst-model/" \
    --statuses "open,on_hold,complete" \
    --dedupe-by-id true \
    --keep 120

Notes:
- Keeps each snapshot minimal: id, ts_utc, origin, status_order, tickets_by_status.
- Appends to an array at signals/tickets.json. If the file doesn't exist,
  it will be created. If it contains a single object, it will be converted
  to an array [object] and then appended.
- Accepts common aliases and normalizes: "paused"→"on_hold", "completed"→"complete".
"""

import argparse
import datetime as dt
import json
import os
from typing import List, Dict, Any

try:
    import yaml
except ImportError as e:
    raise SystemExit("PyYAML is required. Install with: pip install pyyaml") from e


ALIASES = {
    "paused": "on_hold",
    "hold": "on_hold",
    "completed": "complete",
    "done": "complete",
}

def iso_utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def utc_date() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

def load_yaml(path: str) -> Any:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or []

def load_json_any(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            # Best-effort: if someone hand-edited into JSON Lines, parse lines
            f.seek(0)
            items = []
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            return items or None

def normalize_status(s: str) -> str:
    s = (s or "").strip().lower()
    return ALIASES.get(s, s)

def build_buckets(tickets: List[Dict[str, Any]], statuses: List[str], default_module: str) -> Dict[str, List[Dict[str, str]]]:
    buckets = {s: [] for s in statuses}
    for t in tickets:
        status = normalize_status(t.get("status", ""))
        if status not in buckets:
            # Skip statuses we’re not signaling (minimal file)
            continue
        tid = t.get("id")
        if not tid:
            continue
        module = t.get("module") or default_module
        buckets[status].append({"id": tid, "module": module})
    return buckets

def as_array(existing: Any) -> List[Any]:
    if existing is None:
        return []
    if isinstance(existing, list):
        return existing
    # If a dict/object was there from the seed, promote to array
    return [existing]

def dedupe_by_id_keep_latest(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """If multiple snapshots share the same 'id', keep only the last (latest) one."""
    seen = {}
    for i, obj in enumerate(items):
        obj_id = obj.get("id")
        if obj_id:
            seen[obj_id] = i
    # Keep indices that are the last occurrence of each id, plus any without id
    keep_indices = set(seen.values())
    result = []
    for i, obj in enumerate(items):
        if obj.get("id") is None or i in keep_indices:
            result.append(obj)
    return result

def main():
    parser = argparse.ArgumentParser(description="Append Catalyst tickets snapshot")
    parser.add_argument("--in", dest="in_path", default="seeds/tickets.yml")
    parser.add_argument("--out", dest="out_path", default="signals/tickets.json")
    parser.add_argument("--name", dest="origin_name", default="FourTwenty • The Catalyst")
    parser.add_argument("--module", dest="origin_module", default=os.getenv("CATALYST_MODULE", "catalyst-model"))
    parser.add_argument("--emoji", dest="origin_emoji", default="⚙️")
    parser.add_argument("--url", dest="origin_url", default="https://zbreeden.github.io/catalyst-model/")
    parser.add_argument(
        "--statuses",
        dest="statuses",
        default="open,on_hold,complete",
        help="Comma-separated list; order determines status_order in the signal.",
    )
    parser.add_argument(
        "--dedupe-by-id",
        dest="dedupe",
        default="true",
        choices=["true", "false"],
        help="If true, keep only the latest snapshot per id (default: true).",
    )
    parser.add_argument(
        "--keep",
        dest="keep",
        type=int,
        default=0,
        help="If >0, keep only the last N snapshots after appending (rolling window).",
    )
    args = parser.parse_args()

    tickets = load_yaml(args.in_path)
    statuses = [s.strip() for s in args.statuses.split(",") if s.strip()]

    buckets = build_buckets(tickets, statuses, args.origin_module)

    snapshot = {
        "id": f"{utc_date()}-catalyst-tickets",
        "ts_utc": iso_utc_now(),
        "origin": {
            "name": args.origin_name,
            "module": args.origin_module,
            "emoji": args.origin_emoji,
            "url": args.origin_url,
        },
        "status_order": statuses,
        "tickets_by_status": buckets,
    }

    # Load existing file (object or array) and append
    existing = load_json_any(args.out_path)
    arr = as_array(existing)
    arr.append(snapshot)

    # Optional dedupe (by snapshot id)
    if args.dedupe.lower() == "true":
        arr = dedupe_by_id_keep_latest(arr)

    # Optional rolling window
    if args.keep and args.keep > 0 and len(arr) > args.keep:
        arr = arr[-args.keep :]

    # Ensure directory exists
    os.makedirs(os.path.dirname(args.out_path), exist_ok=True)

    with open(args.out_path, "w", encoding="utf-8") as f:
        json.dump(arr, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # Console summary
    counts = {k: len(v) for k, v in buckets.items()}
    total = sum(counts.values())
    print(
        f"Appended snapshot to {args.out_path} (now {len(arr)} total) "
        f"— {total} tickets this run → {counts}"
    )

if __name__ == "__main__":
    main()

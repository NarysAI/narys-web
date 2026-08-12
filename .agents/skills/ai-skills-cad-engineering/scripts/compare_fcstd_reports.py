#!/usr/bin/env python3
"""Compare two reports emitted by inspect_fcstd.py."""

import argparse
import json
import math
import sys


def load(path):
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("schema") != 1 or not isinstance(data.get("objects"), list):
        raise SystemExit("Unsupported inspection report: " + path)
    return data


def close(a, b, tolerance):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=tolerance, abs_tol=tolerance)
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return all(close(x, y, tolerance) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys():
        return all(close(a[key], b[key], tolerance) for key in a)
    return a == b


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--allow", action="append", default=[], help="Object name allowed to change; repeat as needed")
    parser.add_argument("--tolerance", type=float, default=1e-7)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    baseline = load(args.baseline)
    candidate = load(args.candidate)
    old = {item["name"]: item for item in baseline["objects"]}
    new = {item["name"]: item for item in candidate["objects"]}
    added = sorted(new.keys() - old.keys())
    removed = sorted(old.keys() - new.keys())
    changed = sorted(name for name in old.keys() & new.keys() if not close(old[name], new[name], args.tolerance))
    unexpected = sorted(name for name in changed if name not in set(args.allow))
    result = {
        "baselineSha256": baseline.get("sha256"),
        "candidateSha256": candidate.get("sha256"),
        "added": added,
        "removed": removed,
        "changed": changed,
        "unexpectedChanged": unexpected,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for key in ("added", "removed", "changed", "unexpectedChanged"):
            print(f"{key}: {', '.join(result[key]) if result[key] else '-'}")
    return 2 if unexpected else 0


if __name__ == "__main__":
    sys.exit(main())

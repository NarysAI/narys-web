#!/usr/bin/env python3
"""Inspect a FreeCAD document and emit stable JSON evidence.

Run with FreeCADCmd/FreeCADCmd.exe, not ordinary Python.
"""

import argparse
import hashlib
import json
import os
import sys

try:
    import FreeCAD as App
except ImportError as exc:
    raise SystemExit("Run this script with FreeCADCmd so the FreeCAD module is available") from exc


def vector(value):
    return [round(float(value.x), 9), round(float(value.y), 9), round(float(value.z), 9)]


def rotation(value):
    quaternion = value.Q
    return [round(float(item), 12) for item in quaternion]


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def shape_report(obj):
    shape = getattr(obj, "Shape", None)
    if shape is None or shape.isNull():
        return None
    bounds = shape.BoundBox
    return {
        "valid": bool(shape.isValid()),
        "solids": len(shape.Solids),
        "shells": len(shape.Shells),
        "faces": len(shape.Faces),
        "edges": len(shape.Edges),
        "volume": round(float(shape.Volume), 9),
        "bounds": [
            round(float(bounds.XMin), 9), round(float(bounds.XMax), 9),
            round(float(bounds.YMin), 9), round(float(bounds.YMax), 9),
            round(float(bounds.ZMin), 9), round(float(bounds.ZMax), 9),
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=os.environ.get("CAD_FCSTD_FILE"))
    parser.add_argument("--output")
    args = parser.parse_args()
    if not args.file:
        raise SystemExit("Provide --file or set CAD_FCSTD_FILE")
    if not args.output:
        args.output = os.environ.get("CAD_REPORT_OUTPUT")
    source = os.path.abspath(args.file)
    if not os.path.isfile(source):
        raise SystemExit("FCStd file not found: " + source)

    document = App.openDocument(source)
    try:
        document.recompute()
        objects = []
        for obj in sorted(document.Objects, key=lambda item: item.Name.lower()):
            placement = getattr(obj, "Placement", None)
            entry = {
                "name": obj.Name,
                "label": obj.Label,
                "type": obj.TypeId,
                "group": sorted(child.Name for child in getattr(obj, "Group", []) or []),
                "state": list(obj.State),
                "shape": shape_report(obj),
            }
            if placement is not None:
                entry["placement"] = {
                    "base": vector(placement.Base),
                    "rotationQ": rotation(placement.Rotation),
                }
            objects.append(entry)
        report = {
            "schema": 1,
            "file": os.path.basename(source),
            "sha256": sha256(source),
            "label": document.Label,
            "objectCount": len(objects),
            "objects": objects,
        }
    finally:
        App.closeDocument(document.Name)

    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
    else:
        sys.stdout.write(payload)


if __name__ == "__main__":
    main()

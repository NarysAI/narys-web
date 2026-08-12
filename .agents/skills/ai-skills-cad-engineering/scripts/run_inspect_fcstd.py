#!/usr/bin/env python3
"""Invoke inspect_fcstd.py through FreeCADCmd without argument collisions."""

import argparse
import json
import os
import pathlib
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--freecad", default="FreeCADCmd.exe" if os.name == "nt" else "FreeCADCmd")
    parser.add_argument("--file", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    source = pathlib.Path(args.file).resolve()
    output = pathlib.Path(args.output).resolve()
    if not source.is_file():
        raise SystemExit("FCStd file not found: " + str(source))
    output.parent.mkdir(parents=True, exist_ok=True)

    inspector = pathlib.Path(__file__).with_name("inspect_fcstd.py").resolve()
    environment = os.environ.copy()
    environment["CAD_FCSTD_FILE"] = str(source)
    environment["CAD_REPORT_OUTPUT"] = str(output)
    script_literal = json.dumps(str(inspector))
    command = "import runpy,sys; sys.argv=[%s]; runpy.run_path(%s, run_name='__main__')" % (
        script_literal,
        script_literal,
    )
    result = subprocess.run([args.freecad, "-c", command], env=environment, check=False)
    if result.returncode:
        return result.returncode
    if not output.is_file():
        print("FreeCAD completed without creating the inspection report", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())

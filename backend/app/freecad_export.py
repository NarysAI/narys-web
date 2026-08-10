from __future__ import annotations

import sys
from pathlib import Path

import FreeCAD as App
import Mesh
import MeshPart
import Part


def release_step_source(source: Path) -> Path | None:
    """Find the release STEP derivative that belongs to an FCStd master."""
    release_dir = source.parent.parent
    step_dir = release_dir / "STEP"
    for suffix in (".step", ".STEP", ".stp", ".STP"):
        candidate = step_dir / f"{source.stem}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def main() -> int:
    source, destination = Path(sys.argv[1]), sys.argv[2]
    document = App.openDocument(str(source))
    shapes = []
    for obj in document.Objects:
        shape = getattr(obj, "Shape", None)
        if shape is not None and not shape.isNull() and shape.Solids:
            shapes.extend(shape.Solids)
    if not shapes:
        step_source = release_step_source(source)
        if step_source is not None:
            step_shape = Part.read(str(step_source))
            if not step_shape.isNull() and step_shape.Solids:
                shapes.extend(step_shape.Solids)
    if not shapes:
        raise RuntimeError("FreeCAD document and its release STEP derivative have no printable solid")
    combined = Mesh.Mesh()
    for shape in shapes:
        mesh = MeshPart.meshFromShape(
            Shape=shape,
            LinearDeflection=0.08,
            AngularDeflection=0.35,
            Relative=False,
        )
        combined.addMesh(mesh)
    combined.write(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

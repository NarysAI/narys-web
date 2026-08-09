from __future__ import annotations

import sys

import FreeCAD as App
import Mesh
import MeshPart


def main() -> int:
    source, destination = sys.argv[1], sys.argv[2]
    document = App.openDocument(source)
    shapes = []
    for obj in document.Objects:
        shape = getattr(obj, "Shape", None)
        if shape is not None and not shape.isNull() and shape.Solids:
            shapes.extend(shape.Solids)
    if not shapes:
        raise RuntimeError("FreeCAD document has no printable solid")
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

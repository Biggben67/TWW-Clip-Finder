"""Load viewer-exported Collada collision meshes as ``region_tris``.

This is intentionally narrow: the TWW collision viewer exports room collision as
triangle ``polylist`` geometries instanced in a visual scene. The static DZB path
is still preferred when it matches the live/viewer triangle count, but DAE is a
useful calibration source when the viewer includes movable/background collision
that the plain room DZB cache is missing.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET

from tww_sim.core.collision import Tri


def _tag(name: str) -> str:
    return "{http://www.collada.org/2005/11/COLLADASchema}%s" % name


def _id(elem):
    return elem.attrib.get("id")


def _floats(text):
    return [float(x) for x in (text or "").split()]


def _ints(text):
    return [int(x) for x in (text or "").split()]


def _mat_mul(a, b):
    return tuple(
        sum(a[r * 4 + k] * b[k * 4 + c] for k in range(4))
        for r in range(4)
        for c in range(4)
    )


def _transform_point(m, p):
    x, y, z = p
    return (
        m[0] * x + m[1] * y + m[2] * z + m[3],
        m[4] * x + m[5] * y + m[6] * z + m[7],
        m[8] * x + m[9] * y + m[10] * z + m[11],
    )


def _parse_geometries(root):
    geometries = {}
    for geom in root.findall(".//%s/%s" % (_tag("library_geometries"), _tag("geometry"))):
        gid = _id(geom)
        mesh = geom.find(_tag("mesh"))
        if gid is None or mesh is None:
            continue

        sources = {}
        for src in mesh.findall(_tag("source")):
            sid = _id(src)
            arr = src.find(_tag("float_array"))
            acc = src.find("%s/%s" % (_tag("technique_common"), _tag("accessor")))
            if sid is None or arr is None:
                continue
            stride = int(acc.attrib.get("stride", "3")) if acc is not None else 3
            vals = _floats(arr.text)
            sources[sid] = [tuple(vals[i:i + stride][:3]) for i in range(0, len(vals), stride)]

        vertices = {}
        for verts in mesh.findall(_tag("vertices")):
            vid = _id(verts)
            inp = verts.find(_tag("input"))
            if vid is not None and inp is not None and inp.attrib.get("semantic") == "POSITION":
                vertices[vid] = inp.attrib["source"].lstrip("#")

        tris = []
        for polylist in mesh.findall(_tag("polylist")):
            inputs = polylist.findall(_tag("input"))
            if not inputs:
                continue
            stride = max(int(i.attrib.get("offset", "0")) for i in inputs) + 1
            vertex_offset = None
            vertex_source = None
            for inp in inputs:
                if inp.attrib.get("semantic") != "VERTEX":
                    continue
                vertex_offset = int(inp.attrib.get("offset", "0"))
                vertex_source = vertices.get(inp.attrib["source"].lstrip("#"))
                break
            if vertex_offset is None or vertex_source not in sources:
                continue
            positions = sources[vertex_source]
            vcounts = _ints(polylist.findtext(_tag("vcount")))
            packed = _ints(polylist.findtext(_tag("p")))
            cursor = 0
            for vc in vcounts:
                idx = [packed[cursor + i * stride + vertex_offset] for i in range(vc)]
                cursor += vc * stride
                if vc < 3:
                    continue
                for i in range(1, vc - 1):
                    tris.append((positions[idx[0]], positions[idx[i]], positions[idx[i + 1]]))
        geometries[gid] = tris
    return geometries


def _walk_instances(node, parent_matrix, out):
    mat = parent_matrix
    mat_elem = node.find(_tag("matrix"))
    if mat_elem is not None and mat_elem.text:
        mat = _mat_mul(parent_matrix, tuple(_floats(mat_elem.text)))
    for inst in node.findall(_tag("instance_geometry")):
        url = inst.attrib.get("url", "")
        if url.startswith("#"):
            out.append((url[1:], mat))
    for child in node.findall(_tag("node")):
        _walk_instances(child, mat, out)


def load_dae_region(path):
    """Return ``(region_tris, box, label)`` from a Collada DAE collision export."""
    root = ET.parse(path).getroot()
    geometries = _parse_geometries(root)
    visual = root.find(".//%s/%s" % (_tag("library_visual_scenes"), _tag("visual_scene")))
    instances = []
    ident = (1.0, 0.0, 0.0, 0.0,
             0.0, 1.0, 0.0, 0.0,
             0.0, 0.0, 1.0, 0.0,
             0.0, 0.0, 0.0, 1.0)
    if visual is not None:
        for node in visual.findall(_tag("node")):
            _walk_instances(node, ident, instances)
    if not instances:
        instances = [(gid, ident) for gid in geometries]

    region = []
    poly = 0
    for gid, mat in instances:
        for tri in geometries.get(gid, ()):
            verts = [_transform_point(mat, p) for p in tri]
            T = Tri(verts[0], verts[1], verts[2])
            region.append(dict(poly=poly, v=verts, n=(T.pla.nx, T.pla.ny, T.pla.nz), T=T,
                               source=gid))
            poly += 1
    if not region:
        return [], None, os.path.basename(path)
    xs = [c for t in region for c in (t["v"][0][0], t["v"][1][0], t["v"][2][0])]
    ys = [c for t in region for c in (t["v"][0][1], t["v"][1][1], t["v"][2][1])]
    zs = [c for t in region for c in (t["v"][0][2], t["v"][1][2], t["v"][2][2])]
    return region, (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)), os.path.basename(path)

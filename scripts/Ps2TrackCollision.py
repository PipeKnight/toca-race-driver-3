"""Read PS2 collision meshes and add authored triangles to their spatial grid."""

from collections import defaultdict
import math
import struct

from BuildTrackCollisionOverlay import collision_counts


GRID_SIDE = 256
GRID_CELLS = GRID_SIDE * GRID_SIDE
CELL = struct.Struct(">2H")
REFERENCE = struct.Struct(">H")
VERTEX = struct.Struct("<3H2B")
TRIANGLE = struct.Struct("<3H")
POLYGON = struct.Struct("<H2B")
MAX_XZ = (1 << 24) - 1
MAX_Y = (1 << 16) - 1
CELL_MARGIN = 1.5
# The guest cache entry has 13 header words and 303 polygon slots.
CELL_CAPACITY = 0x4f0 // 4 - 13


class Collision:
    def __init__(self, data):
        vertex_count, triangle_count = collision_counts(data)
        polygon_start = 40 + vertex_count * VERTEX.size
        index_start = polygon_start + triangle_count * POLYGON.size
        grid_start = index_start + triangle_count * TRIANGLE.size
        grid_size, = struct.unpack_from("<I", data, 24)
        grid_end = grid_start + grid_size
        ref_start = grid_start + GRID_CELLS * CELL.size
        if grid_end < ref_start or (grid_end - ref_start) % REFERENCE.size:
            raise ValueError("Invalid collision cell table length")
        self.header = data[:40]
        self.raw_vertices = data[40:polygon_start]
        self.polygons = data[polygon_start:index_start]
        self.indices = data[index_start:grid_start]
        self.starts = tuple(CELL.iter_unpack(data[grid_start:ref_start]))
        self.references = tuple(ref for ref, in REFERENCE.iter_unpack(data[ref_start:grid_end]))
        if (self.starts[0] != (0, 0) or self.starts[-1] != (triangle_count, len(self.references))
                or any(a > c or b > d for (a, b), (c, d) in zip(self.starts, self.starts[1:]))
                or any(ref >= triangle_count for ref in self.references)):
            raise ValueError("Invalid collision cell offsets or triangle references")
        flags = data[(grid_end + 3) & ~3:]
        if grid_end < len(data) and len(flags) != GRID_CELLS // 8:
            raise ValueError("Unrecognized collision edge bitfield")
        self.flags = flags
        self.lower = struct.unpack_from("<3f", data)
        upper = struct.unpack_from("<3f", data, 12)
        self.spans = tuple(hi - lo for lo, hi in zip(self.lower, upper))
        self.vertices = tuple((x | hx << 16, y, z | hz << 16)
                              for y, x, z, hx, hz in VERTEX.iter_unpack(self.raw_vertices))
        self.triangles = tuple(TRIANGLE.iter_unpack(self.indices))

    def world(self, point):
        return tuple(lo + span * value / limit
                     for lo, span, value, limit in zip(self.lower, self.spans, point, (MAX_XZ, MAX_Y, MAX_XZ)))

    def packed(self, point):
        if not all(math.isfinite(value) for value in point):
            raise ValueError("Collision vertices must be finite")
        normalized = tuple((value - lo) / span for value, lo, span in zip(point, self.lower, self.spans))
        if not all(0 <= value <= 1 for value in normalized):
            raise ValueError(f"Collision vertex {point} lies outside the template bounds")
        return tuple(round(value * limit) for value, limit in zip(normalized, (MAX_XZ, MAX_Y, MAX_XZ)))


def read_triangles(path):
    vertices = []
    triangles = []
    with path.open(encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, 1):
            fields = line.partition("#")[0].split()
            if not fields:
                continue
            if fields[0] == "v":
                if len(fields) != 4:
                    raise ValueError(f"OBJ line {line_number} must have three vertex coordinates")
                vertices.append(tuple(map(float, fields[1:])))
            elif fields[0] == "f":
                if len(fields) != 4:
                    raise ValueError(f"OBJ line {line_number} must be a triangle")
                indices = [int(field.split("/", 1)[0]) for field in fields[1:]]
                face = tuple(index - 1 if index > 0 else len(vertices) + index for index in indices)
                if any(not 0 <= index < len(vertices) for index in face):
                    raise ValueError(f"OBJ line {line_number} refers to a missing vertex")
                triangles.append(face)
    if not triangles:
        raise ValueError("OBJ contains no triangles")
    return vertices, triangles


def footprint(points):
    return (min(p[0] for p in points), max(p[0] for p in points),
            min(p[2] for p in points), max(p[2] for p in points))


def cell_span(start, end, margin):
    first = max(0, (start - margin) >> 16)
    last = min(GRID_SIDE - 1, (end + margin) >> 16)
    return range(first, last + 1)


def neighbors(cell):
    x, z = cell % GRID_SIDE, cell // GRID_SIDE
    for row in range(max(0, z - 1), min(GRID_SIDE, z + 2)):
        for col in range(max(0, x - 1), min(GRID_SIDE, x + 2)):
            yield row * GRID_SIDE + col


def check_cache_capacity(mesh, home_faces, extra_faces, new_bounds, margin_x, margin_z):
    check_cells = set(extra_faces)
    for home in home_faces:
        check_cells.update(neighbors(home))
    old_bounds = {}
    for cell in check_cells:
        x, z = cell % GRID_SIDE, cell // GRID_SIDE
        x0, x1 = (x << 16) - margin_x, ((x + 1) << 16) + margin_x
        z0, z1 = (z << 16) - margin_z, ((z + 1) << 16) + margin_z

        def touches(bounds):
            left, right, near, far = bounds
            return left <= x1 and right >= x0 and near <= z1 and far >= z0

        first_ref = mesh.starts[cell][1]
        last_ref = mesh.starts[min(cell + 1, GRID_CELLS - 1)][1]
        count = last_ref - first_ref + len(extra_faces.get(cell, ()))
        for neighbor in neighbors(cell):
            first = mesh.starts[neighbor][0]
            last = mesh.starts[min(neighbor + 1, GRID_CELLS - 1)][0]
            added = home_faces.get(neighbor, ())
            if neighbor == cell:
                count += last - first + len(added)
            else:
                for number in range(first, last):
                    if number not in old_bounds:
                        old_bounds[number] = footprint(tuple(mesh.vertices[i] for i in mesh.triangles[number]))
                    count += touches(old_bounds[number])
                count += sum(touches(new_bounds[number]) for number in added)
        if count > CELL_CAPACITY:
            raise ValueError(f"Collision cell ({x}, {z}) exceeds the PS2 polygon cache")


def collision_append(args):
    mesh = Collision(args.input.read_bytes())
    if not 0 <= args.surface_from < len(mesh.triangles):
        raise ValueError("Surface source triangle is outside the template mesh")
    surface = mesh.polygons[args.surface_from * POLYGON.size + 2]
    raw, faces = read_triangles(args.obj)
    if len(mesh.vertices) + len(raw) > 65536 or len(mesh.triangles) + len(faces) > 65535:
        raise ValueError("Added geometry exceeds the 16-bit vertex or triangle limit")
    vertices = tuple(mesh.packed(p) for p in raw)
    margin_x = math.ceil(CELL_MARGIN * MAX_XZ / mesh.spans[0]) + 1
    margin_z = math.ceil(CELL_MARGIN * MAX_XZ / mesh.spans[2]) + 1
    home_faces, extra_faces = defaultdict(list), defaultdict(list)
    references = len(mesh.references)
    new_bounds = []
    for number, face in enumerate(faces):
        a, b, c = (vertices[i] for i in face)
        u = tuple(y - x for x, y in zip(a, b))
        v = tuple(y - x for x, y in zip(a, c))
        normal = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        if not any(normal):
            raise ValueError(f"OBJ triangle {number + 1} collapses in the collision coordinates")
        x0, x1, z0, z1 = footprint((a, b, c))
        new_bounds.append((x0, x1, z0, z1))
        home = (z0 >> 16) * GRID_SIDE + (x0 >> 16)
        home_faces[home].append(number)
        nearby = set(neighbors(home))
        for z in cell_span(z0, z1, margin_z):
            for x in cell_span(x0, x1, margin_x):
                cell = z * GRID_SIDE + x
                if cell not in nearby:
                    references += 1
                    if references > 65535:
                        raise ValueError("Added geometry exceeds the 16-bit cell reference limit")
                    extra_faces[cell].append(number)
    if GRID_CELLS - 1 in home_faces or GRID_CELLS - 1 in extra_faces:
        raise ValueError("Authored geometry reaches the final reserved grid cell")
    check_cache_capacity(mesh, home_faces, extra_faces, new_bounds, margin_x, margin_z)

    vertices_out = bytearray(mesh.raw_vertices)
    for x, y, z in vertices:
        vertices_out.extend(VERTEX.pack(y, x & MAX_Y, z & MAX_Y, x >> 16, z >> 16))
    polygons, indices = bytearray(), bytearray()
    old_to_new = [0] * len(mesh.triangles)
    added_to_new = [0] * len(faces)
    added_polygon = POLYGON.pack(0xffff, surface, 0)
    # Preserve each cell's implicit range and insert its authored triangles after it.
    for cell, (start, _) in enumerate(mesh.starts[:-1]):
        end = mesh.starts[cell + 1][0]
        next_polygon = len(polygons) // POLYGON.size
        old_to_new[start:end] = range(next_polygon, next_polygon + end - start)
        polygons.extend(mesh.polygons[start * POLYGON.size:end * POLYGON.size])
        indices.extend(mesh.indices[start * TRIANGLE.size:end * TRIANGLE.size])
        for number in home_faces.get(cell, ()):
            added_to_new[number] = len(polygons) // POLYGON.size
            polygons.extend(added_polygon)
            indices.extend(TRIANGLE.pack(*(i + len(mesh.vertices) for i in faces[number])))

    cells, refs = bytearray(), bytearray()
    implicit = 0
    # Supplemental references use the triangle indices assigned in the first pass.
    for cell, (start, first) in enumerate(mesh.starts[:-1]):
        end, last = mesh.starts[cell + 1]
        cells.extend(CELL.pack(implicit, len(refs) // REFERENCE.size))
        for number in mesh.references[first:last]:
            refs.extend(REFERENCE.pack(old_to_new[number]))
        for number in extra_faces.get(cell, ()):
            refs.extend(REFERENCE.pack(added_to_new[number]))
        implicit += end - start + len(home_faces.get(cell, ()))
    cells.extend(CELL.pack(implicit, references))
    header = bytearray(mesh.header)
    struct.pack_into("<3I", header, 24, len(cells) + len(refs), implicit, len(mesh.vertices) + len(vertices))
    result = header + vertices_out + polygons + indices + cells + refs
    if mesh.flags:
        result.extend(bytes(-len(result) % 4))
        result.extend(mesh.flags)
    Collision(result)
    with args.output.open("xb") as stream:
        stream.write(result)


def collision_export(args):
    mesh = Collision(args.input.read_bytes())
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("# PS2 collision mesh in game coordinates.\n")
        for point in mesh.vertices:
            stream.write("v " + " ".join(map(str, mesh.world(point))) + "\n")
        for a, b, c in mesh.triangles:
            stream.write(f"f {a + 1} {b + 1} {c + 1}\n")

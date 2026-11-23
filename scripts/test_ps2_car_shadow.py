"""Regression checks for the RD3 shadow mesh encoder."""

import math
import struct
import unittest

from Ps2CarShadow import linked_rings, mesh_record


class ShadowMeshTests(unittest.TestCase):
    def test_closed_mesh_stores_outward_normals_and_reversed_winding(self):
        rings = (
            ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1)),
            ((-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)),
        )
        vertices, faces = linked_rings(rings)
        data = mesh_record("shadow_main_body", (0, 0, 0), vertices, faces)
        self.assertEqual(data[:64].rstrip(b"\0"), b"shadow_main_body")
        self.assertEqual(struct.unpack_from("<I4f", data, 64), (8, 0., 0., 0., 1.))
        start = 84 + len(vertices) * 16
        self.assertEqual(struct.unpack_from("<I", data, start)[0], 12)
        self.assertEqual(len(data), start + 4 + len(faces) * 28)
        indices = struct.iter_unpack("<3I", data[start+4:start+4+12*len(faces)])
        normals = struct.iter_unpack("<4f", data[start+4+12*len(faces):])
        for (i, j, k), (*normal, w) in zip(indices, normals, strict=True):
            self.assertEqual(w, 0.)
            self.assertAlmostEqual(math.hypot(*normal), 1.)
            for index in (i, j, k):
                self.assertGreater(sum(a*b for a, b in zip(normal, vertices[index])), 0)

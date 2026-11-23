"""Regression checks for transferring door UVs without moving the door skins."""

import unittest

from ConvertRd2Db5Doors import paint_uv


class DoorPaintTests(unittest.TestCase):
    def test_project_paint_across_the_door_thickness(self):
        paint = (((0.025, 0., 0.), (.1, .7)), ((-0.018, 0., 1.), (.5, .7)),
                 ((-0.040, 1., 0.), (.1, .9)), ((0.012, 1., 1.), (.5, .9)))
        u, v = paint_uv(.5, .5, paint)
        self.assertAlmostEqual(u, .3)
        self.assertAlmostEqual(v, .8)
        # The two shell surfaces differ in X, but meet the same UV at a shared Y/Z corner.
        u, v = paint_uv(0., 1., paint)
        self.assertAlmostEqual(u, .5, places=3)
        self.assertAlmostEqual(v, .7, places=3)

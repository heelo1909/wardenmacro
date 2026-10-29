"""M2: Retina pixel/point conversion at scale 1 and 2, title-bar trim, point-sized frames."""

import numpy as np

from _util import check, run


def main():
    from warden.geometry import Rect
    from warden.platform import retina
    from warden.vision.capture import to_point_size

    for scale in (1.0, 2.0):
        px = retina.point_to_pixel(733, 411, scale)
        check(f"round trip at scale {scale}", retina.pixel_to_point(*px, scale) == (733, 411))
    check("backing scale 2x", retina.backing_scale(3024, 1512) == 2.0)
    d = retina.Display(Rect(0, 0, 1512, 982), 2.0)
    check("windowed title bar trimmed", retina.content_rect(Rect(10, 10, 800, 600), d, 28) == Rect(10, 38, 800, 572))
    check("fullscreen untouched", retina.content_rect(Rect(0, 0, 1512, 982), d, 28) == Rect(0, 0, 1512, 982))
    check("2x frame scaled to points", to_point_size(np.zeros((600, 800, 3), np.uint8), 400, 300).shape == (300, 400, 3))


run(main)

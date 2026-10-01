from tests.fixtures_frames import GREEN_BGR, blank, draw_frac_rect
from warden.vision.color import find_blobs, sample_hsv


class R:
    def __init__(self, lower, upper):
        self.lower, self.upper = lower, upper


GREEN_RANGE = [R((45, 140, 140), (80, 255, 255))]


def test_finds_a_drawn_green_rect_and_reports_fraction_box():
    frame = draw_frac_rect(blank(), (0.40, 0.80, 0.60, 0.92), GREEN_BGR)
    blobs = find_blobs(frame, [0.0, 0.0, 1.0, 1.0], GREEN_RANGE, min_area=0.001, max_area=0.5)
    assert len(blobs) == 1
    b = blobs[0]
    assert abs(b.x1 - 0.40) < 0.01 and abs(b.x2 - 0.60) < 0.01
    assert abs(b.y1 - 0.80) < 0.01 and abs(b.y2 - 0.92) < 0.01
    assert b.fill > 0.9


def test_area_filter_excludes_too_small_and_too_large():
    frame = draw_frac_rect(blank(), (0.0, 0.0, 0.02, 0.02), GREEN_BGR)  # tiny speck
    assert find_blobs(frame, [0, 0, 1, 1], GREEN_RANGE, min_area=0.01, max_area=0.5) == []
    big = draw_frac_rect(blank(), (0.0, 0.0, 1.0, 1.0), GREEN_BGR)
    assert find_blobs(big, [0, 0, 1, 1], GREEN_RANGE, min_area=0.0001, max_area=0.5) == []


def test_aspect_ratio_filter():
    frame = draw_frac_rect(blank(), (0.3, 0.3, 0.7, 0.32), GREEN_BGR)  # wide thin health bar shape
    assert find_blobs(frame, [0, 0, 1, 1], GREEN_RANGE, min_area=0.0005, aspect_min=5, aspect_max=60) != []
    assert find_blobs(frame, [0, 0, 1, 1], GREEN_RANGE, min_area=0.0005, aspect_min=0.1, aspect_max=0.9) == []


def test_roi_confines_the_search():
    frame = draw_frac_rect(blank(), (0.05, 0.05, 0.15, 0.10), GREEN_BGR)
    assert find_blobs(frame, [0.5, 0.5, 1.0, 1.0], GREEN_RANGE, min_area=0.0001) == []
    assert find_blobs(frame, [0.0, 0.0, 0.3, 0.3], GREEN_RANGE, min_area=0.0001) != []


def test_no_ranges_returns_empty():
    assert find_blobs(blank(), [0, 0, 1, 1], []) == []


def test_sample_hsv_covers_the_drawn_colour():
    frame = draw_frac_rect(blank(), (0.2, 0.2, 0.8, 0.8), GREEN_BGR)
    lower, upper = sample_hsv(frame, (0.2, 0.2, 0.8, 0.8))
    blobs = find_blobs(frame, [0, 0, 1, 1], [R(tuple(lower), tuple(upper))], min_area=0.001, max_area=0.5)
    assert len(blobs) == 1

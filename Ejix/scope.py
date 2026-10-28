# SPDX-License-Identifier: GPL-3.0-only
"""Numerical plane validation independent of Fusion objects."""
import math


def coplanar(planes, tolerance=1e-6):
    if not planes:
        return False
    origin, normal = planes[0]
    def unit(vector):
        length = math.sqrt(sum(v*v for v in vector))
        if not math.isfinite(length) or length <= 1e-12:
            raise ValueError('The Profiles plane has no valid normal.')
        return tuple(v/length for v in vector)
    normal = unit(normal)
    for point, direction in planes:
        other = unit(direction)
        if abs(abs(sum(a*b for a, b in zip(normal, other))) - 1) > 1e-10:
            return False
        if abs(sum((p-o)*n for p, o, n in zip(point, origin, normal))) > tolerance:
            return False
    return True

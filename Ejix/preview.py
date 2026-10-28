# SPDX-License-Identifier: GPL-3.0-only
"""Exact transient intersections and graphics. Never creates design geometry."""
from dataclasses import dataclass
from itertools import product

import adsk.core
import adsk.fusion

from . import fusion_adapter as adapter, solid
from .scope import coplanar

TOLERANCE = 1e-7
SUBTRACT_COLOR = (232, 177, 45, 255)
COPY_COLOR = (70, 150, 240, 255)


def frame_for(source):
    entity = adapter.native(source)
    if isinstance(entity, adsk.fusion.Profile):
        sketch = entity.parentSketch
        origin = sketch.sketchToModelSpace(adsk.core.Point3D.create(0, 0, 0))
        x = origin.vectorTo(sketch.sketchToModelSpace(adsk.core.Point3D.create(1, 0, 0)))
        y = origin.vectorTo(sketch.sketchToModelSpace(adsk.core.Point3D.create(0, 1, 0)))
        z = x.crossProduct(y)
    else:
        origin, z = adapter.plane(source)
        z = z.copy()
        z.normalize()
        reference = adsk.core.Vector3D.create(1, 0, 0) if abs(z.x) < .9 else adsk.core.Vector3D.create(0, 1, 0)
        y = z.crossProduct(reference)
        y.normalize()
        x = y.crossProduct(z)
    x.normalize(); y.normalize(); z.normalize()
    frame = adsk.core.Matrix3D.create()
    if not frame.setWithCoordinateSystem(origin, x, y, z):
        raise ValueError('Unable to locate the Profiles plane.')
    return frame


def inverse(matrix):
    result = matrix.copy()
    if not result.invert():
        raise ValueError('The Profiles plane is degenerate.')
    return result


def transformed(manager, body, matrix):
    result = manager.copy(body)
    if not result or not manager.transform(result, matrix):
        raise ValueError('Unable to transform the temporary Eject volume.')
    return result


def section(source, frame_inverse):
    manager = adsk.fusion.TemporaryBRepManager.get()
    entity = adapter.native(source)
    if isinstance(entity, adsk.fusion.BRepFace):
        return transformed(manager, entity, frame_inverse)
    sketch_frame = frame_for(entity)
    wires = []
    for loop in entity.profileLoops:
        curves = []
        for entry in loop.profileCurves:
            curve = entry.geometry.copy()
            if not curve.transformBy(sketch_frame) or not curve.transformBy(frame_inverse):
                raise ValueError('Unable to transform a Profile boundary.')
            curves.append(curve)
        wire, _ = manager.createWireFromCurves(curves)
        if not wire:
            raise ValueError('Unable to close a Profile boundary.')
        wires.append(wire)
    result = manager.createFaceFromPlanarWires(wires)
    if not result:
        raise ValueError('Unable to construct the temporary Profile face.')
    return result


def corners(box):
    return [adsk.core.Point3D.create(x, y, z) for x, y, z in product(
        (box.minPoint.x, box.maxPoint.x), (box.minPoint.y, box.maxPoint.y), (box.minPoint.z, box.maxPoint.z))]


def plane_signature(target):
    if target is None:
        return None
    plane = adapter.target_plane(target)
    return tuple(plane.origin.asArray()) + tuple(plane.normal.asArray())


@dataclass(frozen=True)
class Hit:
    body: object
    volume: object
    original_volume: float
    extracted_volume: float


def profile_groups(profiles, split=False):
    """Group coplanar profiles, retaining each plane's own normal."""
    if split:
        return [[profile] for profile in profiles]
    groups = []
    for profile in profiles:
        point, normal = adapter.plane(profile)
        plane = (tuple(point.asArray()), tuple(normal.asArray()))
        if groups and coplanar([groups[-1][1], plane]):
            groups[-1][0].append(profile)
        else:
            groups.append(([profile], plane))
    return [group for group, _ in groups]


class GroupAnalysis:
    """Analyze each plane independently and unite intersections per source."""
    def __init__(self):
        self.analyses = []
        self.group_hits = []

    def reset(self):
        self.analyses.clear()
        self.group_hits.clear()

    def analyze(self, design, profiles, settings, targets=(), objects=None):
        groups = profile_groups(profiles, settings.region_mode != 'legacy')
        adapter.validate(design, profiles, (), settings, targets, require_bodies=False,
                         allow_multiple_planes=True)
        while len(self.analyses) < len(groups):
            self.analyses.append(Analysis())
        self.group_hits = []
        manager = adsk.fusion.TemporaryBRepManager.get()
        sources = list(objects) if objects is not None else [
            (body, adapter.native(body)) for body in adapter.candidate_bodies(profiles)]
        remaining = [(body, manager.copy(shape)) for body, shape in sources]
        originals = [(body, shape.volume) for body, shape in sources]
        combined = []
        for analysis, group in zip(self.analyses, groups):
            hits = analysis.analyze(design, group, settings, targets, remaining) if remaining else ()
            current = []
            for hit in hits:
                original_volume = next(volume for body, volume in originals if body == hit.body)
                hit = Hit(hit.body, hit.volume, original_volume, hit.extracted_volume)
                index = next((i for i, old in enumerate(combined) if old.body == hit.body), None)
                if index is None:
                    combined.append(Hit(hit.body, manager.copy(hit.volume), hit.original_volume, hit.extracted_volume))
                else:
                    old = combined[index]
                    if not manager.booleanOperation(old.volume, manager.copy(hit.volume),
                                                    adsk.fusion.BooleanTypes.UnionBooleanType):
                        raise ValueError('Unable to combine Profile preview volumes.')
                    combined[index] = Hit(old.body, old.volume, old.original_volume, old.volume.volume)
                current.append(hit)
                if settings.subtract and settings.region_mode != 'combined':
                    index = next(i for i, (body, _) in enumerate(remaining) if body == hit.body)
                    body, shape = remaining[index]
                    if not manager.booleanOperation(shape, manager.copy(hit.volume),
                                                    adsk.fusion.BooleanTypes.DifferenceBooleanType):
                        raise ValueError('Unable to calculate the remaining Object volume.')
                    if not shape.isSolid or shape.volume <= 1e-10:
                        remaining.pop(index)
            self.group_hits.append(tuple(current))
        return tuple(combined)


class Analysis:
    def __init__(self):
        self.sources = ()
        self.source_stamp = None
        self.frame = None
        self.sheets = ()
        self.key = None
        self.candidates = ()
        self.hits = ()

    def reset(self):
        self.__init__()

    def analyze(self, design, profiles, settings, targets=(), objects=None):
        component = adapter.validate(design, profiles, (), settings, targets, require_bodies=False)
        candidates = tuple(body for body, _ in objects) if objects is not None else tuple(adapter.candidate_bodies(profiles))
        sources = tuple(adapter.native(p) for p in profiles)
        stamp = tuple((p.parentSketch.revisionId if isinstance(p, adsk.fusion.Profile)
                       else p.body.revisionId) for p in sources)
        same_sources = len(sources) == len(self.sources) and all(a == b for a, b in zip(sources, self.sources))
        if not same_sources or stamp != self.source_stamp:
            self.frame = frame_for(profiles[0])
            inv = inverse(self.frame)
            self.sheets = tuple(section(p, inv) for p in profiles)
            self.sources, self.source_stamp = sources, stamp
            self.key = None
        geometry = (settings.start, settings.direction, settings.extent, settings.flipped, settings.distance,
                    settings.distance_two, settings.offset, settings.object_offset, settings.object_offset_two,
                    tuple(plane_signature(t) for t in targets[:2]) if settings.extent == 'object' else (),
                    plane_signature(targets[2]) if settings.start == 'object' else None)
        key = geometry + tuple(adapter.native(b).revisionId for b in candidates)
        if objects is not None:
            key += tuple(shape.volume for _, shape in objects)
        same_bodies = len(candidates) == len(self.candidates) and all(a == b for a, b in zip(candidates, self.candidates))
        if key == self.key and same_bodies and objects is None:
            return self.hits
        self.key = None
        self.candidates = candidates
        if not candidates:
            self.hits = ()
            return self.hits
        manager = adsk.fusion.TemporaryBRepManager.get()
        inv = inverse(self.frame)
        points = []
        for body in candidates:
            for point in corners(adapter.native(body).boundingBox):
                point.transformBy(inv)
                points.append(point)
        tool = self.make_tool(design, settings, targets, points, adapter.start_offset(design, profiles, settings, targets))
        hits = []
        for index, candidate in enumerate(candidates):
            body = adapter.native(candidate)
            original = objects[index][1] if objects is not None else body
            result = manager.copy(original)
            # All Boolean operands are temporary. No bRepBodies.add, sketches,
            # native features, body visibility or timeline changes occur here.
            if not manager.booleanOperation(result, manager.copy(tool), adsk.fusion.BooleanTypes.IntersectionBooleanType):
                continue
            if not result.isSolid or result.volume <= 1e-10:
                continue
            hits.append(Hit(candidate, result, original.volume, result.volume))
        self.hits, self.key = tuple(hits), key
        return self.hits

    def make_tool(self, design, settings, targets, points, start):
        units = design.unitsManager
        evaluate = lambda expression: units.evaluateExpression(expression, 'cm')
        radius = max([1., abs(start)] + [max(abs(p.x), abs(p.y), abs(p.z)) for p in points]) * 4 + 10
        low, high = min(p.z for p in points) - radius, max(p.z for p in points) + radius
        manager = adsk.fusion.TemporaryBRepManager.get()

        def cap(prism, target, offset_expression, direction):
            plane = adapter.target_plane(target)
            point, normal = plane.origin.copy(), plane.normal.copy()
            normal.normalize()
            shift = normal.copy(); shift.scaleBy(evaluate(offset_expression)); point.translateBy(shift)
            inv = inverse(self.frame)
            point.transformBy(inv); normal.transformBy(inv); normal.normalize()
            if abs(normal.z) <= TOLERANCE:
                raise ValueError('To Object cannot be parallel to the extrusion direction.')
            # Orient a temporary half-space with its outer face exactly on the
            # selected target plane, including a slanted plane and signed offset.
            boundary = adsk.core.Point3D.create(0, 0, (normal.x*point.x + normal.y*point.y + normal.z*point.z)/normal.z)
            if (boundary.z - start) * direction <= TOLERANCE:
                raise ValueError('To Object is behind the start plane. Use Flip or choose another Object.')
            if normal.z * direction < 0:
                normal.scaleBy(-1)
            reference = adsk.core.Vector3D.create(1, 0, 0) if abs(normal.x) < .9 else adsk.core.Vector3D.create(0, 1, 0)
            y = normal.crossProduct(reference); y.normalize()
            x = y.crossProduct(normal); x.normalize()
            size = (radius + abs(boundary.z)) * 8
            center = boundary.copy(); inward = normal.copy(); inward.scaleBy(-size/2); center.translateBy(inward)
            box = manager.createBox(adsk.core.OrientedBoundingBox3D.create(center, x, y, size, size, size))
            if not box or not manager.booleanOperation(prism, box, adsk.fusion.BooleanTypes.IntersectionBooleanType):
                raise ValueError('The To Object plane does not enclose an extrusion volume.')
            return prism

        def prism(a, b):
            result = None
            for sheet in self.sheets:
                piece = solid.extrude([sheet], min(a, b), max(a, b))
                if result is None:
                    result = piece
                elif not manager.booleanOperation(result, piece, adsk.fusion.BooleanTypes.UnionBooleanType):
                    raise ValueError('Unable to merge the selected Profile volumes.')
            return result

        if settings.extent == 'distance':
            one = evaluate(settings.distance)
            two = evaluate(settings.distance_two) if settings.direction == 'two' else 0
            if settings.direction == 'symmetric':
                result = prism(start-one, start+one)
            elif settings.direction == 'two':
                result = prism(start-two, start+one)
            else:
                result = prism(start, start-one if settings.flipped else start+one)
        elif settings.extent == 'all':
            result = prism(low if settings.direction != 'one' or settings.flipped else start,
                           high if settings.direction != 'one' or not settings.flipped else start)
        elif settings.direction == 'two':
            result = cap(prism(start, high), targets[0], settings.object_offset, 1)
            other = cap(prism(low, start), targets[1], settings.object_offset_two, -1)
            if not manager.booleanOperation(result, other, adsk.fusion.BooleanTypes.UnionBooleanType):
                raise ValueError('Unable to join the two To Object extents.')
        else:
            direction = -1 if settings.flipped else 1
            result = cap(prism(low if settings.flipped else start, start if settings.flipped else high),
                         targets[0], settings.object_offset, direction)
        if not manager.transform(result, self.frame):
            raise ValueError('Unable to position the Eject volume.')
        return result


class Renderer:
    def __init__(self):
        self.group = None
        self.bodies = []

    def clear(self):
        group, self.group = self.group, None
        if group and group.isValid:
            group.deleteMe()
        self.bodies.clear()

    def show(self, design, hits, profiles, subtract):
        self.clear()
        if not hits:
            return
        self.group = design.rootComponent.customGraphicsGroups.add()
        self.group.isSelectable = False
        color = adsk.core.Color.create(*(SUBTRACT_COLOR if subtract else COPY_COLOR))
        manager = adsk.fusion.TemporaryBRepManager.get()
        context = getattr(profiles[0], 'assemblyContext', None)
        try:
            for hit in hits:
                body = manager.copy(hit.volume)
                self.bodies.append(body)
                if context and not manager.transform(body, context.transform2):
                    raise ValueError('Unable to position the preview in the selected occurrence.')
                graphic = self.group.addBRepBody(body)
                graphic.isSelectable = False
                graphic.color = adsk.fusion.CustomGraphicsShowThroughColorEffect.create(color, .5)
                graphic.depthPriority = 10
                if not graphic.setOpacity(.55, True):
                    raise ValueError('Unable to set the preview transparency.')
        except Exception:
            self.clear()
            raise

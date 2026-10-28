# SPDX-License-Identifier: GPL-3.0-only
"""Native feature backend. All mutations belong to the Fusion command transaction."""
import adsk.core
import adsk.fusion

from .scope import coplanar


class FaceSnapshot:
    """Transient copy of a source face consumed later in the feature timeline."""
    def __init__(self, face):
        self.component = owner(face)
        self.assemblyContext = getattr(face, 'assemblyContext', None)
        self.origin, self.normal = plane(face)
        self.origin, self.normal = self.origin.copy(), self.normal.copy()
        self.sheet = adsk.fusion.TemporaryBRepManager.get().copy(native(face))
        if not self.sheet or self.sheet.faces.count != 1:
            raise ValueError('Unable to preserve the Eject source face for editing.')
        self.nativeObject = self.sheet.faces.item(0)

    @property
    def isValid(self):
        return bool(self.nativeObject and self.nativeObject.isValid)


def native(entity):
    return entity.nativeObject or entity


def collection(entities):
    result = adsk.core.ObjectCollection.create()
    for entity in entities:
        result.add(entity)
    return result


def value(expression):
    return adsk.core.ValueInput.createByString(expression)


def owner(entity):
    if isinstance(entity, FaceSnapshot):
        return entity.component
    entity = native(entity)
    if isinstance(entity, adsk.fusion.Profile):
        return entity.parentSketch.parentComponent
    if isinstance(entity, adsk.fusion.BRepFace):
        return entity.body.parentComponent
    if isinstance(entity, adsk.fusion.BRepBody):
        return entity.parentComponent
    if isinstance(entity, adsk.fusion.ConstructionPlane):
        return entity.component
    raise ValueError('Select sketch Profiles, planar faces and solid Objects.')


def plane(entity):
    if isinstance(entity, FaceSnapshot):
        return entity.origin.copy(), entity.normal.copy()
    entity = native(entity)
    if isinstance(entity, adsk.fusion.Profile):
        sketch = entity.parentSketch
        origin = sketch.sketchToModelSpace(adsk.core.Point3D.create(0, 0, 0))
        tip = sketch.sketchToModelSpace(adsk.core.Point3D.create(0, 0, 1))
        return origin, origin.vectorTo(tip)
    if isinstance(entity, adsk.fusion.BRepFace) and isinstance(entity.geometry, adsk.core.Plane):
        normal = entity.geometry.normal.copy()
        if entity.isParamReversed:
            normal.scaleBy(-1)
        return entity.geometry.origin, normal
    raise ValueError('Profiles must be closed sketch regions or planar faces.')


def face_normal(face):
    """Return the outward normal of a solid planar face, or None."""
    geometry = face.geometry
    if not isinstance(geometry, adsk.core.Plane):
        return None
    body = native(face).body
    if not isinstance(body, adsk.fusion.BRepBody) or not body.isSolid:
        return None
    normal = geometry.normal.copy()
    if face.isParamReversed:
        normal.scaleBy(-1)
    normal.normalize()
    return normal


def solid_bodies(component):
    return [body for body in component.bRepBodies
            if body.isSolid and body.volume > 1e-10]


def inside(body, point):
    return body.pointContainment(point) == adsk.fusion.PointContainment.PointInsidePointContainment


def probe(point, direction, distance):
    result = point.copy()
    result.translateBy(adsk.core.Vector3D.create(direction.x * distance,
                                                 direction.y * distance,
                                                 direction.z * distance))
    return result


def inferred_support_normal(profile):
    """Find the face support geometrically when referencePlane cannot resolve.

    Fusion refuses referencePlane for a face once later features have changed
    the body ("need to roll timeline back before sketch"). The profile itself
    is still valid, so the supporting plane is recovered from the model: first
    a planar face under the profile centroid, then material containment on both
    sides of the sketch plane.
    """
    sketch = profile.parentSketch
    point = sketch.sketchToModelSpace(profile.areaProperties().centroid)
    tolerance = max(adsk.core.Application.get().pointTolerance * 10.0, 1e-5)
    bodies = solid_bodies(sketch.parentComponent)
    for body in bodies:
        for face in body.faces:
            if not isinstance(face.geometry, adsk.core.Plane) or not face.isPointOnFace(point, tolerance):
                continue
            normal = face_normal(face)
            if normal is None:
                continue
            if inside(body, probe(point, normal, tolerance)):
                continue
            if inside(body, probe(point, normal, -tolerance)):
                return normal
    _, direction = plane(profile)
    direction.normalize()
    for sign in (1.0, -1.0):
        if any(inside(body, probe(point, direction, sign * tolerance)) for body in bodies):
            direction.scaleBy(-sign)
            return direction
    return None


def support_normal(profile):
    """Return the outward normal of the planar face a sketch is built on.

    A sketch created on a body face keeps its own Z axis, which Fusion may
    orient away from the material. The face normal is the reliable reference
    for pointing an Eject inward; None means the sketch is not supported by a
    solid face and no preference can be derived.
    """
    entity = native(profile)
    if not isinstance(entity, adsk.fusion.Profile):
        return None
    sketch = entity.parentSketch
    if not sketch.isParametric:
        return None
    try:
        support = sketch.referencePlane
    except Exception:
        return inferred_support_normal(entity)
    if not isinstance(support, adsk.fusion.BRepFace):
        return None
    return face_normal(support)


def unique(entities):
    result = []
    for entity in entities:
        # Entity tokens are deliberately not compared; Fusion tokens can change.
        if not any(entity == existing for existing in result):
            result.append(entity)
    return result


def validate(design, profiles, bodies, settings, targets=(), require_bodies=True, allow_multiple_planes=False):
    if not design or design.designType != adsk.fusion.DesignTypes.ParametricDesignType:
        raise ValueError('Eject requires Capture Design History.')
    if not profiles:
        raise ValueError('Select Profiles.')
    if require_bodies and not bodies:
        raise ValueError('Enable at least one Object to eject.')
    if any(not entity.isValid for entity in (*profiles, *bodies)):
        raise ValueError('A selected entity is no longer available. Select it again.')
    component = owner(profiles[0])
    if any(owner(entity) != component for entity in (*profiles, *bodies)):
        raise ValueError('Profiles and Objects must belong to the same component.')
    contexts = [getattr(entity, 'assemblyContext', None) for entity in (*profiles, *bodies)]
    if any(context != contexts[0] for context in contexts):
        raise ValueError('Select Profiles and Objects from the same component occurrence.')
    if any(not isinstance(native(body), adsk.fusion.BRepBody) or not native(body).isSolid for body in bodies):
        raise ValueError('Objects must be solid BRep bodies.')
    planes = [plane(entity) for entity in profiles]
    if not allow_multiple_planes and not coplanar([(tuple(p.asArray()), tuple(n.asArray())) for p, n in planes]):
        raise ValueError('All Profiles and faces must lie on the same plane.')
    units = design.unitsManager
    def evaluate(expression):
        if not units.isValidExpression(expression, 'cm'):
            raise ValueError('Enter a valid length expression: ' + expression)
        return units.evaluateExpression(expression, 'cm')
    settings.validate(evaluate)
    if settings.start == 'object':
        start_offset(design, profiles, settings, targets)
    if settings.extent == 'object':
        needed = 2 if settings.direction == 'two' else 1
        if len(targets) < needed or any(target is None for target in targets[:needed]):
            raise ValueError('Select an Object for each To Object direction.')
        for target in targets[:needed]:
            if not target.isValid or owner(target) != component:
                raise ValueError('To Object must be a face or plane in the source component.')
            if getattr(target, 'assemblyContext', None) != contexts[0]:
                raise ValueError('To Object must be in the same component occurrence.')
            target_plane(target)
    return component


def start_offset(design, profiles, settings, targets=()):
    """Start distance along the local profile normal, shared by preview/arrows."""
    if settings.start == 'profile':
        return 0.
    offset = design.unitsManager.evaluateExpression(settings.offset, 'cm')
    if settings.start == 'offset':
        return offset
    if len(targets) < 3 or targets[2] is None:
        raise ValueError('Select a Start Object.')
    source, target = profiles[0], targets[2]
    if not target.isValid or owner(target) != owner(source) or getattr(target, 'assemblyContext', None) != getattr(source, 'assemblyContext', None):
        raise ValueError('Start Object must be in the source component occurrence.')
    origin, normal = plane(source)
    normal = normal.copy(); normal.normalize()
    geometry = target_plane(target)
    target_normal = geometry.normal.copy(); target_normal.normalize()
    target_entity = native(target)
    if isinstance(target_entity, adsk.fusion.BRepFace):
        ok, target_normal = target_entity.evaluator.getNormalAtPoint(target_entity.pointOnFace)
        if not ok:
            raise ValueError('Unable to determine the Start Object normal.')
        target_normal.normalize()
    if abs(abs(normal.dotProduct(target_normal)) - 1) > 1e-7:
        raise ValueError('Start Object currently requires a plane parallel to the Profiles plane.')
    return origin.vectorTo(geometry.origin).dotProduct(normal) + offset * normal.dotProduct(target_normal)


def target_plane(entity):
    entity = native(entity)
    if isinstance(entity, adsk.fusion.ConstructionPlane):
        return entity.geometry
    if isinstance(entity, adsk.fusion.BRepFace) and isinstance(entity.geometry, adsk.core.Plane):
        return entity.geometry
    raise ValueError('To Object currently supports planar faces and construction planes.')


def candidate_bodies(profiles):
    component = owner(profiles[0])
    context = getattr(profiles[0], 'assemblyContext', None)
    bodies = []
    for body in component.bRepBodies:
        entity = body.createForAssemblyContext(context) if context else body
        if body.isSolid and entity.isVisible and body.volume > 1e-10:
            bodies.append(entity)
    return bodies


def apply_extent(extrude, settings, targets=()):
    """Works on both ExtrudeFeatureInput and an existing rolled-back feature."""
    participants = list(extrude.participantBodies) if isinstance(extrude, adsk.fusion.ExtrudeFeature) else None
    def extent(expression, side=0):
        if settings.extent == 'all':
            return adsk.fusion.ThroughAllExtentDefinition.create()
        if settings.extent == 'object':
            if len(targets) <= side or targets[side] is None:
                raise ValueError('Select the To Object face or plane.')
            offset = settings.object_offset if side == 0 else settings.object_offset_two
            return adsk.fusion.ToEntityExtentDefinition.create(native(targets[side]), False, value(offset))
        return adsk.fusion.DistanceExtentDefinition.create(value(expression))
    if settings.direction == 'symmetric' and settings.extent == 'distance':
        ok = extrude.setSymmetricExtent(value(settings.distance), False, value('0 deg'))
    elif settings.direction in ('two', 'symmetric'):
        ok = extrude.setTwoSidesExtent(extent(settings.distance), extent(settings.distance_two, 1), value('0 deg'), value('0 deg'))
    else:
        direction = (adsk.fusion.ExtentDirections.NegativeExtentDirection if settings.flipped
                     else adsk.fusion.ExtentDirections.PositiveExtentDirection)
        # Fusion accepts omitted taper on new inputs, but some builds reject
        # that default when redefining an existing ExtrudeFeature.
        ok = extrude.setOneSideExtent(extent(settings.distance), direction, value('0 deg'))
    if not ok:
        raise ValueError('Fusion could not define the Eject extent.')
    if settings.start == 'profile':
        extrude.startExtent = adsk.fusion.ProfilePlaneStartDefinition.create()
    elif settings.start == 'offset':
        extrude.startExtent = adsk.fusion.OffsetStartDefinition.create(value(settings.offset))
    else:
        if len(targets) < 3 or targets[2] is None:
            raise ValueError('Select a Start Object.')
        extrude.startExtent = adsk.fusion.FromEntityStartDefinition.create(native(targets[2]), value(settings.offset))
    if participants is not None:
        # Redefining an extent makes Fusion discover participants again. Keep
        # Intersect limited to its copied source, including during feature edit.
        extrude.participantBodies = participants


def healthy(feature):
    if not feature:
        raise ValueError('Fusion could not create the Eject operation.')
    if feature.healthState == adsk.fusion.FeatureHealthStates.ErrorFeatureHealthState:
        raise ValueError(feature.errorOrWarningMessage or 'Fusion could not compute the Eject operation.')
    return feature


class Backend:
    def __init__(self, component, targets=()):
        self.component = component
        self.design = component.parentDesign
        self.targets = targets
        self.profiles = ()
        self.originals = []
        self.result_groups = []
        self.first = None
        self.last = None
        self.extrudes = []
        self.created = []
        self.custom = None
        self.multi_groups = False
        self.step_planes = []
        self.extra_nodes = []
        self.source_fragments = []
        self.marker = self.design.timeline.markerPosition
        from .preview import Analysis
        self.analysis = Analysis()

    def track(self, feature, name):
        if feature:
            self.created.append(feature)
        feature = healthy(feature)
        feature.name = name
        if self.first is None:
            self.first = feature
        self.last = feature
        return feature

    def volume(self, body):
        return body.volume

    def intersection_volume(self, source, profiles, settings):
        hits = self.analysis.analyze(self.design, profiles, settings, self.targets,
                                     objects=[(source, native(source))])
        return sum(hit.extracted_volume for hit in hits)

    def extract(self, source, profiles, settings, excluded=()):
        self.profiles += tuple(profile for profile in profiles if not any(profile == old for old in self.profiles))
        self.originals.append(native(source))
        existing = tuple(self.component.bRepBodies)
        copy = self.track(self.component.features.copyPasteBodies.add(native(source)), 'Ejix Copy')
        if copy.bodies.count != 1:
            raise ValueError('Fusion did not create one source copy.')
        copied_body = copy.bodies.item(0)
        participants = [copied_body]
        if excluded:
            definition = self.component.features.combineFeatures.createInput(copied_body, collection(excluded))
            definition.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
            definition.isKeepToolBodies = True
            cut = self.track(self.component.features.combineFeatures.add(definition), 'Ejix Previous Regions')
            participants = [body for body in cut.bodies if body.isValid and body.isSolid and
                            not any(body == previous for previous in existing)]
            if not participants:
                raise ValueError('No source volume remains for this Profile.')
            if len(participants) > 1:
                intersecting = []
                for body in participants:
                    hits = self.analysis.analyze(self.design, profiles, settings, self.targets,
                                                 objects=[(body, body)])
                    if hits:
                        intersecting.append(body)
                    else:
                        self.track(self.component.features.removeFeatures.add(body), 'Ejix Remove Unused Copy')
                participants = intersecting
                if not participants:
                    raise ValueError('The Profile does not intersect the remaining Object.')
        definition = self.component.features.extrudeFeatures.createInput(
            collection(native(p) for p in profiles), adsk.fusion.FeatureOperations.IntersectFeatureOperation)
        apply_extent(definition, settings, self.targets)
        # An explicit participant list prevents touching the original or any
        # earlier result, even if they overlap the same extrusion.
        definition.participantBodies = participants
        intersect = self.track(self.component.features.extrudeFeatures.add(definition), 'Ejix Intersect')
        self.extrudes.append(intersect)
        # For face profiles, Fusion also reports the unchanged face-owner body
        # in ExtrudeFeature.bodies. Only bodies from this new copy are results;
        # originals and previously extracted pieces must never become tools.
        result = tuple(body for body in intersect.bodies
                       if not any(body == previous for previous in existing))
        self.result_groups.append(list(result))
        for index, body in enumerate(result):
            body.name = 'Ejix ' + source.name + (' ' + str(index + 1) if len(result) > 1 else '')
            body.isVisible = True
        return result

    def subtract(self, source, pieces):
        definition = self.component.features.combineFeatures.createInput(native(source), collection(pieces))
        definition.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
        definition.isKeepToolBodies = True
        feature = self.track(self.component.features.combineFeatures.add(definition), 'Ejix Cut')
        self.extra_nodes.append((native(source), feature))
        fragments = [body for body in feature.bodies if body.isValid and body.isSolid and
                     not any(body == piece for piece in pieces)]
        if not fragments:
            raise ValueError('The Eject cut did not leave a source Object.')
        self.source_fragments.append((native(source), fragments, feature))

    def merge_connected(self, source, pieces):
        """Join intersecting or face-connected solids; retain disconnected pieces."""
        manager = adsk.fusion.TemporaryBRepManager.get()
        pieces = list(pieces)
        while True:
            joined_pair = False
            for i, first in enumerate(pieces):
                for j in range(i + 1, len(pieces)):
                    other = pieces[j]
                    temporary = manager.copy(first)
                    if not manager.booleanOperation(temporary, manager.copy(other),
                            adsk.fusion.BooleanTypes.UnionBooleanType):
                        continue
                    if temporary.lumps.count >= first.lumps.count + other.lumps.count:
                        continue
                    definition = self.component.features.combineFeatures.createInput(first, collection([other]))
                    definition.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
                    definition.isKeepToolBodies = False
                    feature = self.track(self.component.features.combineFeatures.add(definition), 'Ejix Join')
                    self.extra_nodes.append((native(source), feature))
                    for group in self.result_groups:
                        group[:] = [body for body in group if body != other]
                    pieces.pop(j)
                    joined_pair = True
                    break
                if joined_pair:
                    break
            if not joined_pair:
                return pieces

    def to_component(self, body, index):
        slots = [(group, i) for group in self.result_groups for i, item in enumerate(group) if item == body]
        occurrence = self.component.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        if not occurrence:
            raise ValueError('Fusion could not create the result component.')
        self.created.append(occurrence)
        occurrence.component.name = 'Ejix ' + str(index)
        moved = body.moveToComponent(occurrence)
        if not moved:
            raise ValueError('Fusion could not move the result into its component.')
        for group, i in slots:
            group[i] = native(moved)
        # Moving a body and creating an occurrence add native timeline nodes.
        # Include the actual final node rather than stopping at Combine.
        self.last = self.design.timeline.item(self.design.timeline.markerPosition - 1).entity
        if self.last != occurrence:
            self.created.append(self.last)
        return moved

    def finish(self, settings):
        if settings.execution == 'eject':
            from . import feature
            return feature.group(self, settings)
        group = self.design.timeline.timelineGroups.add(
            self.first.timelineObject.index, self.last.timelineObject.index)
        if not group:
            raise ValueError('Fusion could not group the native Eject operations.')
        group.name = 'Eject'
        group.isCollapsed = True
        return None

    def update_moved_results(self, custom):
        from . import feature
        feature.save_moved_results(custom, self.result_groups)

    def abort(self):
        """executePreview has no executeFailed rollback flag; clean partial work."""
        failures = []
        if self.custom and self.custom.isValid:
            try:
                self.custom.timelineObject.rollTo(True)
                if not self.custom.setStartAndEndFeatures(None, None):
                    raise RuntimeError('Unable to ungroup the failed preview.')
                if not self.custom.deleteMe():
                    raise RuntimeError('Unable to remove the failed Eject node.')
            except Exception as error:
                failures.append(str(error))
        for item in reversed(self.created):
            try:
                if item.isValid and not item.deleteMe():
                    raise RuntimeError('Unable to remove ' + item.name)
            except Exception as error:
                failures.append(str(error))
        self.design.timeline.markerPosition = min(self.marker, self.design.timeline.count)
        if failures:
            raise RuntimeError('Preview cleanup failed: ' + '; '.join(failures))

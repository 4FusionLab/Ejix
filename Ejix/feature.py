# SPDX-License-Identifier: GPL-3.0-only
"""Experimental named Eject feature, grouping a native parametric operation graph.

Native Copy/Intersect/Cut own the geometry and dependency graph. The custom node
does not depend on modified bodies and never creates geometry during compute.
"""
from dataclasses import replace
from pathlib import Path
import json
import adsk.core
import adsk.fusion

from .settings import Settings
from .fusion_adapter import FaceSnapshot, apply_extent, healthy

DEFINITION_ID = '4FusionLab.Ejix.Parametric'
EDIT_ID = '4FusionLab_Ejix_Edit'
DATA_KEY = 'ejix_v1'
_definition = None
_handler = None
_building = False


class Compute(adsk.fusion.CustomFeatureEventHandler):
    def notify(self, args):
        if _building:
            return
        # Fusion computes the contained native features. No body dependencies:
        # a dependency on a body modified by this span can be self-referential.
        try:
            raw = args.customFeature.customNamedValues.value(DATA_KEY)
            if raw:  # The node is briefly empty while its initial span is built.
                Settings.decode(raw)
        except Exception as error:
            args.computeStatus.statusMessages.addError('DRPOINT_COMPUTE_FAILED', str(error))


def register():
    global _definition, _handler
    if _definition is None or _handler is None:
        ui = adsk.core.Application.get().userInterface
        if not ui.commandDefinitions.itemById(EDIT_ID):
            raise ValueError('Register Edit Eject before registering Eject Feature.')
        definition = adsk.fusion.CustomFeatureDefinition.create(
            DEFINITION_ID, 'Eject', str(Path(__file__).parent / 'resources' / 'eject'))
        if not definition:
            raise ValueError('This Fusion version does not support Eject Feature.')
        definition.editCommandId = EDIT_ID
        handler = Compute()
        if not definition.customFeatureCompute.add(handler):
            raise ValueError('Fusion could not register Eject Feature compute.')
        _definition, _handler = definition, handler
    return _definition


def unregister():
    global _definition, _handler
    if _definition and _handler:
        _definition.customFeatureCompute.remove(_handler)
    _definition = _handler = None


def group(backend, settings):
    global _building
    originals = [body.entityToken for body in backend.originals]
    results = [[body.entityToken for body in group] for group in backend.result_groups]
    definition = backend.component.features.customFeatures.createInput(register())
    # Capture dependencies through native operations instead of saved entity
    # tokens. Adding the custom node before the span mirrors Perfora's working
    # timeline pattern and avoids referencing post-cut topology.
    if not backend.first.timelineObject.rollTo(True):
        raise ValueError('Unable to prepare the Eject timeline.')
    for i, source in enumerate(backend.profiles):
        if not definition.addDependency('source' + str(i), source.nativeObject or source):
            raise ValueError('Unable to capture the Eject Profile dependency.')
    previous_building, _building = _building, True
    try:
        custom = backend.component.features.customFeatures.add(definition)
        if not custom:
            raise ValueError('Unable to create the Eject Feature.')
        backend.custom = custom
        custom.customNamedValues.addOrSetValue(DATA_KEY, settings.encode())
        custom.customNamedValues.addOrSetValue('ejix_originals', json.dumps(originals))
        custom.customNamedValues.addOrSetValue('ejix_results', json.dumps(results))
        custom.customNamedValues.addOrSetValue('ejix_ignored', json.dumps([False] * len(originals)))
    finally:
        _building = previous_building
    if not backend.last.timelineObject.rollTo(False):
        raise ValueError('Unable to restore Eject operations.')
    if not custom.timelineObject.rollTo(True):
        raise ValueError('Unable to group the Eject timeline.')
    if not custom.setStartAndEndFeatures(backend.first, backend.last):
        raise ValueError('Unable to group the Eject operations.')
    owned = list(custom.features)
    extrudes = [item for item in owned if isinstance(item, adsk.fusion.ExtrudeFeature)]
    custom.customNamedValues.addOrSetValue('ejix_nodes', json.dumps(node_groups(custom, owned, extrudes,
                                                                               backend if getattr(backend, 'multi_groups', False) else None)))
    custom.customNamedValues.addOrSetValue('ejix_nodes_schema', '2')
    if getattr(backend, 'multi_groups', False):
        unique = []
        result_groups = []
        steps = []
        for source, result, plane in zip(backend.originals, results, backend.step_planes):
            index = next((i for i, body in enumerate(unique) if body == source), None)
            if index is None:
                index = len(unique)
                unique.append(source)
                result_groups.append([])
            result_groups[index].extend(result)
            steps.append({'object': index, 'plane': plane})
        custom.customNamedValues.addOrSetValue('ejix_originals', json.dumps([body.entityToken for body in unique]))
        custom.customNamedValues.addOrSetValue('ejix_results', json.dumps(result_groups))
        custom.customNamedValues.addOrSetValue('ejix_ignored', json.dumps([False] * len(unique)))
        custom.customNamedValues.addOrSetValue('ejix_steps', json.dumps(steps))
        custom.customNamedValues.addOrSetValue('ejix_layout', '3')
        if backend.source_fragments:
            fragment_groups = []
            cut_nodes = []
            for source in unique:
                record = next((entry for entry in backend.source_fragments if entry[0] == source), None)
                fragment_groups.append([body.entityToken for body in record[1]] if record else [source.entityToken])
                cut_nodes.append(owned.index(record[2]) if record else None)
            custom.customNamedValues.addOrSetValue('ejix_fragments', json.dumps(fragment_groups))
            custom.customNamedValues.addOrSetValue('ejix_cut_nodes', json.dumps(cut_nodes))
    if not custom.timelineObject.rollTo(False):
        raise ValueError('Unable to restore the Eject timeline.')
    return custom


def sources(custom):
    result = []
    index = 0
    missing = False
    while True:
        dependency = custom.dependencies.itemById('source' + str(index))
        if not dependency:
            break
        if not dependency.entity or not dependency.entity.isValid:
            missing = True
        else:
            result.append(dependency.entity)
        index += 1
    if result and not missing:
        return result
    if missing and hasattr(custom, 'timelineObject'):
        design = custom.parentComponent.parentDesign
        marker = design.timeline.markerPosition
        anchor = design.timeline.item(marker - 1) if marker else None
        try:
            if not custom.timelineObject.rollTo(True):
                raise ValueError('Unable to locate the upstream Eject sources.')
            upstream = [custom.dependencies.itemById('source' + str(i)).entity for i in range(index)]
            if all(entity and entity.isValid for entity in upstream):
                return [FaceSnapshot(entity) if isinstance(entity, adsk.fusion.BRepFace) else entity
                        for entity in upstream]
            recovered_upstream = []
            for extrusion in (f for f in custom.features if isinstance(f, adsk.fusion.ExtrudeFeature)):
                profile = extrusion.profile
                for entity in (list(profile) if isinstance(profile, adsk.core.ObjectCollection) else [profile]):
                    if entity and entity.isValid and not any(entity == old for old in recovered_upstream):
                        recovered_upstream.append(entity)
            if len(recovered_upstream) == index:
                return [FaceSnapshot(entity) if isinstance(entity, adsk.fusion.BRepFace) else entity
                        for entity in recovered_upstream]
        finally:
            if anchor and anchor.isValid:
                anchor.rollTo(False)
            else:
                design.timeline.markerPosition = min(marker, design.timeline.count)
    recovered = []
    for extrusion in (f for f in custom.features if isinstance(f, adsk.fusion.ExtrudeFeature)):
        profile = extrusion.profile
        for entity in (list(profile) if isinstance(profile, adsk.core.ObjectCollection) else [profile]):
            if entity and entity.isValid and not any(entity == old for old in recovered):
                recovered.append(entity)
    if not recovered or missing and len(recovered) != index:
        raise ValueError('An upstream Eject Profile is unavailable. Restore the source geometry.')
    return recovered


def targets(custom):
    extrusion = next(f for f in custom.features if isinstance(f, adsk.fusion.ExtrudeFeature))
    start = adsk.fusion.FromEntityStartDefinition.cast(extrusion.startExtent)
    one = adsk.fusion.ToEntityExtentDefinition.cast(extrusion.extentOne) if not extrusion.symmetricExtent else None
    two = adsk.fusion.ToEntityExtentDefinition.cast(extrusion.extentTwo) if extrusion.hasTwoExtents else None
    return (one.entity if one else None, two.entity if two else None, start.entity if start else None)


def resolve_body(custom, token):
    # Saved tokens are resolved through Fusion; token strings are never used to
    # compare entity identity. They add no dependency on this feature's results.
    bodies = custom.parentComponent.parentDesign.findEntityByToken(token)
    if not bodies:
        raise ValueError('An Eject Object is unavailable. Restore the upstream geometry.')
    body = adsk.fusion.BRepBody.cast(bodies[0])
    if not body or not body.isValid:
        raise ValueError('An Eject Object is no longer a solid body.')
    return body.nativeObject or body


def original_bodies(custom):
    raw = custom.customNamedValues.value('ejix_originals')
    if not raw:
        raise ValueError('Recreate this Eject Feature to enable graphical editing.')
    return [resolve_body(custom, token) for token in json.loads(raw)]


def preview_objects(custom):
    originals = original_bodies(custom)
    groups = json.loads(custom.customNamedValues.value('ejix_results'))
    if len(groups) != len(originals):
        raise ValueError('The Eject Object mapping is incomplete. Recreate the Eject Feature.')
    manager = adsk.fusion.TemporaryBRepManager.get()
    ignored = ignored_objects(custom, len(originals))
    raw_fragments = custom.customNamedValues.value('ejix_fragments')
    fragments = json.loads(raw_fragments) if raw_fragments else None
    if fragments is not None and len(fragments) != len(originals):
        raise ValueError('The Eject Object fragment mapping is incomplete.')
    result = []
    for index, (original, tokens) in enumerate(zip(originals, groups)):
        restored = manager.copy(original)
        for token in (() if not fragments else fragments[index]):
            fragment = resolve_body(custom, token)
            if fragment != original and not manager.booleanOperation(restored, manager.copy(fragment),
                                                                      adsk.fusion.BooleanTypes.UnionBooleanType):
                raise ValueError('Unable to reconstruct the split Eject Object.')
        for token in (() if ignored[index] else tokens):
            body = resolve_body(custom, token)
            if not manager.booleanOperation(restored, manager.copy(body), adsk.fusion.BooleanTypes.UnionBooleanType):
                raise ValueError('Unable to reconstruct an Object for the graphical edit preview.')
        result.append((original, restored))
    return result


def capture_fragments(custom, owned, ignored):
    """Track every remaining body when a source cut splits it into pieces."""
    raw = custom.customNamedValues.value('ejix_cut_nodes')
    if not raw:
        return
    nodes = json.loads(raw)
    originals = original_bodies(custom)
    groups = []
    for index, node_index in enumerate(nodes):
        if node_index is None or ignored[index]:
            groups.append([originals[index].entityToken])
            continue
        cut = owned[node_index]
        if not cut.timelineObject.rollTo(True):
            raise ValueError('Unable to inspect the Eject cut tools.')
        tools = list(cut.toolBodies)
        if not cut.timelineObject.rollTo(False):
            raise ValueError('Unable to restore the Eject cut.')
        fragments = [body for body in cut.bodies if body.isValid and body.isSolid and
                     not any(body == tool for tool in tools)]
        if not fragments:
            raise ValueError('The edited Eject source fragments are unavailable.')
        groups.append([body.entityToken for body in fragments])
    if owned and not owned[-1].timelineObject.rollTo(False):
        raise ValueError('Unable to restore the Eject operations.')
    custom.customNamedValues.addOrSetValue('ejix_fragments', json.dumps(groups))


def ignored_objects(custom, count):
    raw = custom.customNamedValues.value('ejix_ignored')
    return json.loads(raw) if raw else [False] * count


def save_moved_results(custom, result_groups):
    """Refresh result tokens after moves outside the parent custom feature."""
    raw = custom.customNamedValues.value('ejix_steps')
    steps = json.loads(raw) if raw else [{'object': i} for i in range(len(result_groups))]
    count = len(json.loads(custom.customNamedValues.value('ejix_originals')))
    results = [[] for _ in range(count)]
    for step, group in zip(steps, result_groups):
        results[step['object']].extend(body.entityToken for body in group)
    custom.customNamedValues.addOrSetValue('ejix_results', json.dumps(results))
    custom.customNamedValues.addOrSetValue('ejix_external_moves', '1')


def node_groups(custom, owned, extrudes, backend=None):
    raw = custom.customNamedValues.value('ejix_nodes')
    if raw and custom.customNamedValues.value('ejix_nodes_schema') == '2':
        return json.loads(raw)
    # Legacy migration: Copy[/BaseFeature]/Intersect per source,
    # followed by Cuts and (for components) create/move pairs per result.
    copies = [i for i, item in enumerate(owned) if item.objectType == 'adsk::fusion::CopyPasteBody']
    ends = [owned.index(item) for item in extrudes]
    if len(copies) != len(ends):
        raise ValueError('Recreate this Eject Feature to update participating Objects.')
    groups = [list(range(start, end + 1)) for start, end in zip(copies, ends)]
    if backend is not None:
        for body, node in backend.extra_nodes:
            if node in owned:
                index = next(i for i, source in enumerate(backend.originals) if source == body)
                groups[index].append(owned.index(node))
        return groups
    cuts = [i for i, item in enumerate(owned) if isinstance(item, adsk.fusion.CombineFeature)]
    for group, index in zip(groups, cuts):
        group.append(index)
    used = {index for group in groups for index in group}
    tail = [i for i in range(len(owned)) if i not in used]
    results = json.loads(custom.customNamedValues.value('ejix_results'))
    if tail:
        if len(tail) != 2 * sum(map(len, results)):
            raise ValueError('Recreate this Eject Feature to update result components.')
        for group, bodies in zip(groups, results):
            count = 2 * len(bodies)
            group.extend(tail[:count]); del tail[:count]
    return groups


def capture_results(custom, extrudes, ignored):
    """A removed and restored copy can receive a new persistent body token."""
    protected = original_bodies(custom)
    protected.extend(source.body for source in sources(custom) if isinstance(source, adsk.fusion.BRepFace))
    groups = json.loads(custom.customNamedValues.value('ejix_results'))
    steps = json.loads(custom.customNamedValues.value('ejix_steps')) if custom.customNamedValues.value('ejix_layout') == '3' else None
    if steps:
        groups = [[] if not ignored[index] else group for index, group in enumerate(groups)]
    for index, extrusion in enumerate(extrudes):
        object_index = steps[index]['object'] if steps else index
        if ignored[object_index]:
            continue
        bodies = [body for body in extrusion.bodies if body.isValid and body.isSolid and body.volume > 1e-10
                  and not any(body == original for original in protected)]
        if not bodies:
            raise ValueError('The edited Eject result is unavailable.')
        if steps:
            groups[object_index].extend(body.entityToken for body in bodies)
        else:
            groups[index] = [body.entityToken for body in bodies]
    custom.customNamedValues.addOrSetValue('ejix_results', json.dumps(groups))


def read(custom):
    settings = Settings.decode(custom.customNamedValues.value(DATA_KEY))
    extrudes = [f for f in custom.features if isinstance(f, adsk.fusion.ExtrudeFeature)]
    if not extrudes:
        raise ValueError('The Eject Feature has lost its Intersect operation.')
    # The native Parameters dialog can change expressions outside our dialog.
    # Reflect those edits rather than restoring stale copies from metadata.
    first = extrudes[0]
    symmetric = first.symmetricExtent
    one = adsk.fusion.DistanceExtentDefinition.cast(first.extentOne) if not symmetric else None
    two = adsk.fusion.DistanceExtentDefinition.cast(first.extentTwo) if first.hasTwoExtents else None
    offset = adsk.fusion.OffsetStartDefinition.cast(first.startExtent)
    changes = {}
    if symmetric:
        expression = symmetric.distance.expression
        changes['distance'] = '(' + expression + ') / 2' if symmetric.isFullLength else expression
    if one:
        changes['distance'] = one.distance.expression
    if two:
        changes['distance_two'] = two.distance.expression
    to_one = adsk.fusion.ToEntityExtentDefinition.cast(first.extentOne) if not symmetric else None
    to_two = adsk.fusion.ToEntityExtentDefinition.cast(first.extentTwo) if first.hasTwoExtents else None
    if to_one:
        changes['object_offset'] = to_one.offset.expression
    if to_two:
        changes['object_offset_two'] = to_two.offset.expression
    if offset:
        changes['start'] = 'offset'
        changes['offset'] = offset.offset.expression
    else:
        entity_start = adsk.fusion.FromEntityStartDefinition.cast(first.startExtent)
        changes['start'] = 'object' if entity_start else 'profile'
        if entity_start:
            changes['offset'] = entity_start.offset.expression
    return replace(settings, **changes)


def edit_graph(owned, groups, extrudes, settings, targets, ignored):
    """Remove the ignored source copy; preserve upstream body identities."""
    for group, extrusion, skip in zip(groups, extrudes, ignored):
        end = owned.index(extrusion)
        if skip:
            for index in reversed(group):
                if index > end and not owned[index].isSuppressed:
                    owned[index].isSuppressed = True
    for extrusion, skip in zip(extrudes, ignored):
        if not extrusion.timelineObject.rollTo(True):
            raise ValueError('Unable to edit the Intersect extent.')
        # A wholly enclosed copied body can be removed by the same extrusion.
        # Suppressing Copy instead would invalidate persistent downstream tools.
        operation = (adsk.fusion.FeatureOperations.CutFeatureOperation if skip
                     else adsk.fusion.FeatureOperations.IntersectFeatureOperation)
        if extrusion.operation != operation:
            participants = list(extrusion.participantBodies)
            extrusion.operation = operation
            extrusion.participantBodies = participants
        apply_extent(extrusion, settings, targets)
        if not extrusion.timelineObject.rollTo(False):
            raise ValueError('Unable to compute the edited Intersect.')
        healthy(extrusion)
    for group, extrusion, skip in zip(groups, extrudes, ignored):
        if skip:
            continue
        end = owned.index(extrusion)
        for index in group:
            if index > end and owned[index].isSuppressed:
                owned[index].isSuppressed = False
    if not owned[-1].timelineObject.rollTo(False):
        raise ValueError('Unable to compute Eject operations.')
    for item in owned:
        if not item.isSuppressed and hasattr(item, 'healthState'):
            healthy(item)


def update(custom, settings, new_targets=()):
    """Update extents and ignore whole/missed sources without deleting nodes."""
    from . import preview, engine
    previous = read(custom)
    previous_targets = targets(custom)
    if (settings.result, settings.subtract, settings.region_mode) != (previous.result, previous.subtract, previous.region_mode):
        raise ValueError('Result type, Profile Results and Subtract are fixed for an existing Eject Feature.')
    design = custom.parentComponent.parentDesign
    marker = design.timeline.markerPosition
    anchor = design.timeline.item(marker - 1) if marker else None
    owned = list(custom.features)
    extrudes = [f for f in owned if isinstance(f, adsk.fusion.ExtrudeFeature)]
    if not owned or not extrudes:
        raise ValueError('The Eject Feature has lost its native operations.')
    groups = node_groups(custom, owned, extrudes)
    objects = preview_objects(custom)
    grouped = custom.customNamedValues.value('ejix_layout') == '3'
    analysis = preview.GroupAnalysis() if grouped else preview.Analysis()
    hits = analysis.analyze(design, sources(custom), settings, new_targets, objects)
    ignored = []
    for original, restored in objects:
        hit = next((hit for hit in hits if hit.body == original), None)
        if hit is None:
            raise ValueError('The new extent misses an existing Eject Object. Adjust the extent or recreate Eject.')
        ignored.append(settings.subtract and engine.fully_enclosed(restored.volume, hit.extracted_volume))
    previous_ignored = ignored_objects(custom, len(objects))
    external_moves = custom.customNamedValues.value('ejix_external_moves') == '1'
    if external_moves and ignored != previous_ignored:
        raise ValueError('Changing whole-body participation in component results requires recreating Eject.')
    if custom.customNamedValues.value('ejix_fragments') and ignored != previous_ignored:
        raise ValueError('Changing whole-body participation in a multi-profile Eject requires recreating it.')
    if grouped:
        steps = json.loads(custom.customNamedValues.value('ejix_steps'))
        if len(steps) != len(extrudes) or len(groups) != len(extrudes):
            raise ValueError('The Eject Feature operation mapping is incomplete.')
        expected = {(step['plane'], step['object']) for step in steps if not ignored[step['object']]}
        actual = {(plane, index) for plane, plane_hits in enumerate(analysis.group_hits)
                  for index, (body, _) in enumerate(objects)
                  if not ignored[index] and any(hit.body == body for hit in plane_hits)}
        if expected != actual:
            raise ValueError('The new extent changes which Profile planes intersect an Object. Recreate Eject to change its operation graph.')
        step_ignored = [ignored[step['object']] for step in steps]
        previous_step_ignored = [previous_ignored[step['object']] for step in steps]
    else:
        step_ignored = ignored
        previous_step_ignored = previous_ignored
    try:
        if not custom.timelineObject.rollTo(True) or not custom.setStartAndEndFeatures(None, None):
            raise ValueError('Unable to edit the Eject timeline.')
        edit_graph(owned, groups, extrudes, settings, new_targets, step_ignored)
        capture_fragments(custom, owned, ignored)
        if not custom.timelineObject.rollTo(True) or not custom.setStartAndEndFeatures(owned[0], owned[-1]):
            raise ValueError('Unable to regroup Eject operations.')
        custom.customNamedValues.addOrSetValue(DATA_KEY, settings.encode())
        custom.customNamedValues.addOrSetValue('ejix_nodes', json.dumps(groups))
        custom.customNamedValues.addOrSetValue('ejix_nodes_schema', '2')
        custom.customNamedValues.addOrSetValue('ejix_ignored', json.dumps(ignored))
        if not custom.timelineObject.rollTo(False):
            raise ValueError('Unable to restore the edited Eject timeline.')
        if not external_moves and settings.region_mode != 'combined':
            capture_results(custom, extrudes, ignored)
        if grouped:
            # Moves to child components are downstream of the custom node.
            # Restore them before checking that the edited graph still matches
            # all participating Profile volumes in the fresh preview.
            if anchor and anchor.isValid:
                anchor.rollTo(False)
            else:
                design.timeline.markerPosition = min(marker, design.timeline.count)
            result_groups = json.loads(custom.customNamedValues.value('ejix_results'))
            for index, (body, restored) in enumerate(objects):
                if ignored[index]:
                    continue
                if settings.region_mode == 'combined':
                    expected_volume = next(hit.extracted_volume for hit in hits if hit.body == body)
                else:
                    expected_volume = sum(hit.extracted_volume for plane_hits in analysis.group_hits
                                          for hit in plane_hits if hit.body == body)
                actual_volume = sum(resolve_body(custom, token).volume for token in result_groups[index])
                if abs(actual_volume - expected_volume) > max(1e-8, restored.volume * 1e-7):
                    raise ValueError('The edited Eject no longer matches its preview. Recreate Eject for the new intersection.')
    except Exception:
        custom.timelineObject.rollTo(True)
        custom.setStartAndEndFeatures(None, None)
        edit_graph(owned, groups, extrudes, previous, previous_targets, previous_step_ignored)
        capture_fragments(custom, owned, previous_ignored)
        custom.timelineObject.rollTo(True)
        if not custom.setStartAndEndFeatures(owned[0], owned[-1]):
            raise RuntimeError('Unable to restore Eject after the failed edit.')
        custom.customNamedValues.addOrSetValue(DATA_KEY, previous.encode())
        custom.customNamedValues.addOrSetValue('ejix_ignored', json.dumps(previous_ignored))
        custom.timelineObject.rollTo(False)
        if not external_moves and previous.region_mode != 'combined':
            capture_results(custom, extrudes, previous_ignored)
        raise
    finally:
        if anchor and anchor.isValid:
            anchor.rollTo(False)
        else:
            design.timeline.markerPosition = min(marker, design.timeline.count)

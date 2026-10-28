# SPDX-License-Identifier: GPL-3.0-only
"""Native Fusion fixtures; run explicitly inside Fusion, never during unit tests."""
from dataclasses import replace
import adsk.core
import adsk.fusion
from Ejix import engine, fusion_adapter
from Ejix.settings import Settings


def overlapping_planes_case():
    """Verify ordered intersections and separate preview graphics in Fusion."""
    from Ejix import preview
    app = adsk.core.Application.get()
    doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        root = design.rootComponent
        sketch = root.sketches.add(root.xYConstructionPlane)
        sketch.sketchCurves.sketchLines.addTwoPointRectangle(
            adsk.core.Point3D.create(0, 0, 0), adsk.core.Point3D.create(4, 4, 0))
        extrusion = root.features.extrudeFeatures.addSimple(sketch.profiles.item(0),
            adsk.core.ValueInput.createByString('4 cm'), adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        body = extrusion.bodies.item(0)
        sketch.isVisible = False
        profiles = []
        for plane, xyz in ((root.xYConstructionPlane, (2, 2, 0)), (root.yZConstructionPlane, (0, 2, 2))):
            sketch = root.sketches.add(plane)
            center = sketch.modelToSketchSpace(adsk.core.Point3D.create(*xyz))
            sketch.sketchCurves.sketchCircles.addByCenterRadius(center, 1)
            profiles.append(sketch.profiles.item(0))
            sketch.isVisible = False
        settings = Settings(execution='native', distance='3 cm')
        analysis = preview.GroupAnalysis()
        hits = analysis.analyze(design, profiles, settings)
        parts = [hit for group in analysis.group_hits for hit in group]
        assert len(parts) == 2 and parts[0].extracted_volume > parts[1].extracted_volume > 0
        renderer = preview.Renderer()
        try:
            renderer.show(design, parts, profiles, True)
            assert len(renderer.bodies) == 2
        finally:
            renderer.clear()
        result = engine.eject_groups(fusion_adapter.Backend(root), preview.profile_groups(profiles),
                                     hits, analysis.group_hits, settings)
        assert len(result.bodies) == 2
        for piece, hit in zip(result.bodies, parts):
            assert abs(piece.volume - hit.extracted_volume) < 1e-6
        assert abs(body.volume + sum(piece.volume for piece in result.bodies) - 64) < 1e-6
        assert design.computeAll()
        return [piece.volume for piece in result.bodies]
    finally:
        doc.close(False)


def multiplane_feature_case(result='body', subtract=True, region_mode='separate'):
    """Create and edit an ordered, overlapping two-plane Custom Feature."""
    import importlib
    module = runtime()
    feature = importlib.import_module(module.__name__ + '.feature')
    app = adsk.core.Application.get()
    doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        root = design.rootComponent
        sketch = root.sketches.add(root.xYConstructionPlane)
        sketch.sketchCurves.sketchLines.addTwoPointRectangle(
            adsk.core.Point3D.create(0, 0, 0), adsk.core.Point3D.create(4, 4, 0))
        original = root.features.extrudeFeatures.addSimple(sketch.profiles.item(0),
            adsk.core.ValueInput.createByString('4 cm'), adsk.fusion.FeatureOperations.NewBodyFeatureOperation).bodies.item(0)
        sketch.isVisible = False
        profiles = []
        for plane, xyz in ((root.xYConstructionPlane, (2, 2, 0)), (root.yZConstructionPlane, (0, 2, 2))):
            sketch = root.sketches.add(plane)
            center = sketch.modelToSketchSpace(adsk.core.Point3D.create(*xyz))
            sketch.sketchCurves.sketchCircles.addByCenterRadius(center, 1)
            profiles.append(sketch.profiles.item(0))
            sketch.isVisible = False
        settings = module.Settings(execution='eject', result=result, subtract=subtract,
                                   region_mode=region_mode, distance='3 cm')
        analysis = module.preview.GroupAnalysis()
        hits = analysis.analyze(design, profiles, settings)
        output = module.engine.eject_groups(module.adapter.Backend(root), module.preview.profile_groups(profiles, True),
                                            hits, analysis.group_hits, settings)
        custom = output.feature
        expected_count = 1 if region_mode == 'combined' else 2
        assert custom and len(output.bodies) == expected_count and len(feature.sources(custom)) == 2
        for distance in ('2.5 cm', '3 cm'):
            edited = replace(settings, distance=distance)
            objects = feature.preview_objects(custom)
            assert abs(objects[0][1].volume - 64) < 1e-6
            analysis = module.preview.GroupAnalysis()
            hits = analysis.analyze(design, feature.sources(custom), edited, feature.targets(custom), objects)
            expected = ([hit.extracted_volume for hit in hits] if region_mode == 'combined' else
                        [hit.extracted_volume for group in analysis.group_hits for hit in group])
            feature.update(custom, edited, feature.targets(custom))
            groups = __import__('json').loads(custom.customNamedValues.value('ejix_results'))
            actual = [feature.resolve_body(custom, token).volume for group in groups for token in group]
            assert len(actual) == len(expected) == expected_count
            assert all(abs(a - b) < 1e-6 for a, b in zip(actual, expected)), (actual, expected)
            assert design.computeAll()
        return {'result': result, 'subtract': subtract, 'regions': region_mode,
                'remaining': original.volume, 'results': actual}
    finally:
        doc.close(False)


def split_source_feature_case(result='body', roundtrip=False):
    """A previous region splits a source; later regions must reach all fragments."""
    import importlib
    module = runtime()
    feature = importlib.import_module(module.__name__ + '.feature')
    app = adsk.core.Application.get()
    doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        root = design.rootComponent
        sketch = root.sketches.add(root.xYConstructionPlane)
        sketch.sketchCurves.sketchLines.addTwoPointRectangle(
            adsk.core.Point3D.create(0, 0, 0), adsk.core.Point3D.create(6, 2, 0))
        root.features.extrudeFeatures.addSimple(sketch.profiles.item(0),
            adsk.core.ValueInput.createByString('2 cm'), adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        sketch.isVisible = False
        sketch = root.sketches.add(root.xYConstructionPlane)
        sketch.sketchCurves.sketchLines.addTwoPointRectangle(
            adsk.core.Point3D.create(2.5, 0, 0), adsk.core.Point3D.create(3.5, 2, 0))
        first = sketch.profiles.item(0)
        sketch.isVisible = False
        sketch = root.sketches.add(root.yZConstructionPlane)
        p0 = sketch.modelToSketchSpace(adsk.core.Point3D.create(0, 0, 0))
        p1 = sketch.modelToSketchSpace(adsk.core.Point3D.create(0, 1, 1))
        sketch.sketchCurves.sketchLines.addTwoPointRectangle(p0, p1)
        second = sketch.profiles.item(0)
        sketch.isVisible = False
        settings = module.Settings(execution='eject', result=result, distance='6 cm')
        profiles = [first, second]
        analysis = module.preview.GroupAnalysis()
        hits = analysis.analyze(design, profiles, settings)
        output = module.engine.eject_groups(module.adapter.Backend(root), module.preview.profile_groups(profiles, True),
                                            hits, analysis.group_hits, settings)
        custom = output.feature
        assert sorted(round(body.volume, 6) for body in output.bodies) == [2.5, 2.5, 4.0]
        assert abs(feature.preview_objects(custom)[0][1].volume - 24) < 1e-6
        for distance in ('5 cm', '6 cm'):
            feature.update(custom, replace(settings, distance=distance), feature.targets(custom))
            assert abs(feature.preview_objects(custom)[0][1].volume - 24) < 1e-6
            assert design.computeAll()
        if roundtrip:
            import os
            import tempfile
            with tempfile.TemporaryDirectory(prefix='ejix-split-') as folder:
                path = os.path.join(folder, 'split.f3d')
                assert design.exportManager.execute(design.exportManager.createFusionArchiveExportOptions(path))
                reopened = app.importManager.importToNewDocument(app.importManager.createFusionArchiveImportOptions(path))
                try:
                    restored_design = adsk.fusion.Design.cast(app.activeProduct)
                    restored = restored_design.rootComponent.features.customFeatures.item(0)
                    assert abs(feature.preview_objects(restored)[0][1].volume - 24) < 1e-6
                    feature.update(restored, replace(settings, distance='5 cm'), feature.targets(restored))
                    assert abs(feature.preview_objects(restored)[0][1].volume - 24) < 1e-6
                    assert restored_design.computeAll()
                finally:
                    reopened.close(False)
        return {'result': result, 'source_volume': feature.preview_objects(custom)[0][1].volume}
    finally:
        doc.close(False)


def consumed_face_feature_case():
    """Edit a feature after its first source face and a copied fragment disappear."""
    import importlib
    module = runtime()
    feature = importlib.import_module(module.__name__ + '.feature')
    app = adsk.core.Application.get()
    doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        root = design.rootComponent
        sketch = root.sketches.add(root.xYConstructionPlane)
        sketch.sketchCurves.sketchLines.addTwoPointRectangle(
            adsk.core.Point3D.create(0, 0, 0), adsk.core.Point3D.create(6, 2, 0))
        body = root.features.extrudeFeatures.addSimple(sketch.profiles.item(0),
            adsk.core.ValueInput.createByString('2 cm'), adsk.fusion.FeatureOperations.NewBodyFeatureOperation).bodies.item(0)
        sketch.isVisible = False
        definition = root.constructionPlanes.createInput()
        definition.setByOffset(root.xYConstructionPlane, adsk.core.ValueInput.createByString('2 cm'))
        top_plane = root.constructionPlanes.add(definition)
        sketch = root.sketches.add(top_plane)
        p0 = sketch.modelToSketchSpace(adsk.core.Point3D.create(2.5, 0, 2))
        p1 = sketch.modelToSketchSpace(adsk.core.Point3D.create(3.5, 2, 2))
        sketch.sketchCurves.sketchLines.addTwoPointRectangle(p0, p1)
        root.features.extrudeFeatures.addSimple(sketch.profiles.item(0),
            adsk.core.ValueInput.createByString('1 cm'), adsk.fusion.FeatureOperations.JoinFeatureOperation)
        sketch.isVisible = False
        face = next(face for face in body.faces if isinstance(face.geometry, adsk.core.Plane)
                    and abs(face.pointOnFace.z - 3) < 1e-6)
        definition = root.constructionPlanes.createInput()
        definition.setByOffset(root.xZConstructionPlane, adsk.core.ValueInput.createByString('2 cm'))
        side_plane = root.constructionPlanes.add(definition)
        sketch = root.sketches.add(side_plane)
        p0 = sketch.modelToSketchSpace(adsk.core.Point3D.create(0, 2, 0))
        p1 = sketch.modelToSketchSpace(adsk.core.Point3D.create(2, 2, 1))
        sketch.sketchCurves.sketchLines.addTwoPointRectangle(p0, p1)
        profiles = [face, sketch.profiles.item(0)]
        sketch.isVisible = False
        settings = module.Settings(execution='eject', distance='6 cm', flipped=True)
        analysis = module.preview.GroupAnalysis()
        hits = analysis.analyze(design, profiles, settings)
        output = module.engine.eject_groups(module.adapter.Backend(root), module.preview.profile_groups(profiles, True),
                                            hits, analysis.group_hits, settings)
        custom = output.feature
        assert len(output.bodies) == 2, (len(output.bodies), [[hit.extracted_volume for hit in group]
                                                               for group in analysis.group_hits])
        assert abs(feature.preview_objects(custom)[0][1].volume - 26) < 1e-6
        assert feature.sources(custom)[0].isValid
        feature.update(custom, replace(settings, distance='5 cm'), feature.targets(custom))
        assert abs(feature.preview_objects(custom)[0][1].volume - 26) < 1e-6
        assert design.computeAll()
        return {'results': len(output.bodies), 'restored_source': feature.preview_objects(custom)[0][1].volume}
    finally:
        doc.close(False)


def fixture(name='Ejix Acceptance', count=2):
    app = adsk.core.Application.get()
    doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    doc.name = name
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent
    for index in range(count):
        x = index * 6
        sketch = root.sketches.add(root.xYConstructionPlane)
        sketch.sketchCurves.sketchLines.addTwoPointRectangle(
            adsk.core.Point3D.create(x, 0, 0), adsk.core.Point3D.create(x + 4, 4, 0))
        extrusion = root.features.extrudeFeatures.addSimple(sketch.profiles.item(0),
            adsk.core.ValueInput.createByString('4 cm'), adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        extrusion.bodies.item(0).name = 'Source ' + str(index + 1)
        sketch.isVisible = False
    bodies = list(root.bRepBodies)
    region = root.sketches.add(root.xYConstructionPlane)
    region.name = 'Ejix Region'
    region.sketchCurves.sketchLines.addTwoPointRectangle(
        adsk.core.Point3D.create(1, 1, 0), adsk.core.Point3D.create((count - 1) * 6 + 3, 3, 0))
    return doc, design, root, region, bodies


def run_case(execution='native', result='body', subtract=True, close=True):
    doc, design, root, region, originals = fixture('Ejix ' + execution + ' ' + result + ' ' + str(subtract))
    settings = Settings(execution=execution, result=result, subtract=subtract, distance='2 cm')
    profile = region.profiles.item(0)
    fusion_adapter.validate(design, [profile], originals, settings)
    output = engine.eject(fusion_adapter.Backend(root), [profile], originals, settings)
    assert len(output.bodies) == 2, 'Both sources must produce a result.'
    assert all(abs(b.volume - 12) < 1e-6 for b in output.bodies), 'Each extracted volume must be 12 cm^3.'
    expected_original = 52 if subtract else 64
    assert all(abs(b.volume - expected_original) < 1e-6 for b in originals)
    assert root.occurrences.count == (2 if result == 'component' else 0)
    assert design.computeAll(), 'Compute All failed.'
    assert all(abs(b.volume - 12) < 1e-6 for b in output.bodies), 'Recompute changed result volume.'
    errors = [design.timeline.item(i).entity.name for i in range(design.timeline.count)
              if hasattr(design.timeline.item(i).entity, 'healthState')
              and design.timeline.item(i).entity.healthState == adsk.fusion.FeatureHealthStates.ErrorFeatureHealthState]
    assert not errors, str(errors)
    summary = {'execution': execution, 'result': result, 'subtract': subtract,
               'original_volumes': [b.volume for b in originals],
               'result_volumes': [b.volume for b in output.bodies],
               'components': root.occurrences.count, 'timeline': design.timeline.count,
               'custom_owned': len(output.feature.features) if output.feature else 0}
    if close:
        doc.close(False)  # Only this function's disposable, unsaved test document.
    return summary


def runtime():
    import sys
    matches = [module for module in list(sys.modules.values())
               if str(getattr(module, '__file__', '')).endswith('/Ejix.py')
               and len(getattr(module, '_bindings', []))]
    assert len(matches) == 1, 'Start Ejix through Fusion Scripts and Add-Ins first.'
    return matches[0]


def edit_geometry_case():
    """Exercise production in-place edits on a new disposable two-body fixture.

    This checks the modeling path, not native dialog OK/Cancel transactions.
    Run only when no interactive command is active.
    """
    import importlib
    module = runtime()
    feature = importlib.import_module(module.__name__ + '.feature')
    doc, design, root, region, originals = fixture('Ejix edit geometry regression')
    settings = module.Settings(execution='eject', distance='2 cm')
    output = module.engine.eject(module.adapter.Backend(root),
                                 [region.profiles.item(0)], originals, settings)
    custom = output.feature
    marker, count = design.timeline.markerPosition, design.timeline.count
    summaries = []
    for distance, start, offset, expected in (
            ('3 cm', 'profile', '0 mm', 18),
            ('2 cm', 'offset', '5 mm', 12),
            ('2 cm', 'profile', '0 mm', 12)):
        changed = replace(settings, distance=distance, start=start, offset=offset)
        feature.update(custom, changed)
        assert design.computeAll(), 'Recompute failed after editing Eject.'
        assert design.timeline.count == count and design.timeline.markerPosition == marker
        results = [body.volume for body in output.bodies]
        remaining = [body.volume for body in originals]
        assert all(abs(volume - expected) < 1e-6 for volume in results), results
        assert all(abs(volume - (64 - expected)) < 1e-6 for volume in remaining), remaining
        saved = feature.read(custom)
        assert saved.start == start, (saved.start, start)
        summaries.append({'distance': distance, 'start': start, 'offset': offset,
                          'remaining': remaining, 'results': results})
    return summaries


def start_object_case():
    """Compare exact preview/native coordinates for signed Object offsets."""
    import importlib
    module = runtime()
    feature = importlib.import_module(module.__name__ + '.feature')
    doc, design, root, region, originals = fixture('Ejix Start Object acceptance')
    plane_input = root.constructionPlanes.createInput()
    plane_input.setByOffset(root.xYConstructionPlane, adsk.core.ValueInput.createByString('5 mm'))
    plane = root.constructionPlanes.add(plane_input)
    settings = module.Settings(execution='eject', distance='2 cm')
    output = module.engine.eject(module.adapter.Backend(root), [region.profiles.item(0)], originals, settings)
    summaries = []
    for offset, minimum in (('2 mm', .7), ('-2 mm', .3)):
        changed = replace(settings, start='object', offset=offset)
        targets = (None, None, plane)
        feature.update(output.feature, changed, targets)
        assert design.computeAll()
        hits = module.preview.Analysis().analyze(design, [region.profiles.item(0)], changed,
                                                targets, feature.preview_objects(output.feature))
        assert len(hits) == len(output.bodies) == 2
        for body, hit in zip(output.bodies, hits):
            assert abs(body.volume - 12) < 1e-6 and abs(hit.extracted_volume - 12) < 1e-6
            for shape in (body, hit.volume):
                assert abs(shape.boundingBox.minPoint.z - minimum) < 1e-6
                assert abs(shape.boundingBox.maxPoint.z - (minimum + 2)) < 1e-6
        summaries.append({'offset': offset, 'min_z_cm': minimum, 'volume_cm3': 12})
    return summaries


def face_case(execution='native'):
    """Face-owner body must not be counted, renamed, or used as a cut tool."""
    module = runtime()
    doc, design, root, region, originals = fixture('Ejix face ' + execution, count=1)
    face = next(face for face in originals[0].faces if abs(face.pointOnFace.y) < 1e-6)
    settings = module.Settings(execution=execution, distance='10 mm', flipped=True)
    hits = module.preview.Analysis().analyze(design, [face], settings)
    output = module.engine.eject(module.adapter.Backend(root), [face], originals, settings)
    assert len(hits) == len(output.bodies) == 1
    assert abs(hits[0].extracted_volume - 16) < 1e-6
    assert abs(output.bodies[0].volume - 16) < 1e-6
    assert originals[0].name == 'Source 1' and abs(originals[0].volume - 48) < 1e-6
    assert design.computeAll()
    if execution == 'native':
        group = design.timeline.timelineGroups.item(0)
        assert group.name == 'Eject' and group.count == 3 and group.isCollapsed
    return {'execution': execution, 'original_cm3': originals[0].volume,
            'result_cm3': output.bodies[0].volume}


def whole_body_case(execution='native', result='body'):
    """Ignore a whole face-owner while cutting another body from its face."""
    module = runtime()
    doc, design, root, region, originals = fixture('Ejix whole body ' + execution + ' ' + result)
    face = next(face for face in originals[0].faces if abs(face.pointOnFace.x) < 1e-6)
    settings = module.Settings(execution=execution, result=result, distance='8 cm', flipped=True)
    hits = module.preview.Analysis().analyze(design, [face], settings)
    assert [round(hit.extracted_volume, 6) for hit in hits] == [64., 32.]
    output = module.engine.eject(module.adapter.Backend(root), [face], originals, settings)
    assert len(output.bodies) == 1 and abs(output.bodies[0].volume - 32) < 1e-6
    assert [round(body.volume, 6) for body in originals] == [64., 32.]
    assert [body.name for body in originals] == ['Source 1', 'Source 2']
    assert design.computeAll()
    return {'execution': execution, 'result': result, 'original_cm3': [body.volume for body in originals],
            'result_cm3': output.bodies[0].volume}


def face_preview_case():
    """Compare volume and both bounding-box corners on all six cube faces."""
    module = runtime()
    doc, design, root, region, originals = fixture('Ejix 35 mm face preview acceptance', count=1)
    source = originals[0]
    summaries = []
    for face in list(source.faces):
        settings = module.Settings(distance='35 mm', flipped=True, subtract=False)
        hits = module.preview.Analysis().analyze(design, [face], settings, objects=[(source, source)])
        pieces = module.adapter.Backend(root).extract(source, [face], settings)
        assert len(hits) == len(pieces) == 1
        preview, actual = hits[0].volume, pieces[0]
        assert abs(preview.volume - actual.volume) < 1e-6
        assert preview.boundingBox.minPoint.distanceTo(actual.boundingBox.minPoint) < 1e-6
        assert preview.boundingBox.maxPoint.distanceTo(actual.boundingBox.maxPoint) < 1e-6
        summaries.append({'reversed': face.isParamReversed, 'volume_cm3': actual.volume})
    return summaries


def ignored_edit_case(small_first=False):
    """Whole-source exclusion must reverse when an edited extent shrinks."""
    import importlib
    module = runtime()
    feature = importlib.import_module(module.__name__ + '.feature')
    doc, design, root, region, originals = fixture('Ejix ignored edit acceptance', count=1)
    shape = adsk.fusion.TemporaryBRepManager.get().createBox(adsk.core.OrientedBoundingBox3D.create(
        adsk.core.Point3D.create(2, 2, .5), adsk.core.Vector3D.create(1, 0, 0),
        adsk.core.Vector3D.create(0, 1, 0), 1, 1, 1))
    base = root.features.baseFeatures.add()
    base.startEdit()
    try:
        root.bRepBodies.add(shape, base)
    finally:
        base.finishEdit()
    small = base.bodies.item(0)
    small.name = 'Small Source'
    bodies = [small, *originals] if small_first else [*originals, small]
    settings = module.Settings(execution='eject', distance='2.5 mm')
    output = module.engine.eject(module.adapter.Backend(root), [region.profiles.item(0)], bodies, settings)
    for distance, ignored, volume in (('2 cm', True, 1), ('2.5 mm', False, .75)):
        feature.update(output.feature, replace(settings, distance=distance))
        assert design.computeAll()
        expected = [ignored, False] if small_first else [False, ignored]
        assert feature.ignored_objects(output.feature, 2) == expected
        assert abs(small.volume - volume) < 1e-6
        assert abs(feature.preview_objects(output.feature)[bodies.index(small)][1].volume - 1) < 1e-6
    return {'small_first': small_first, 'restored_small_cm3': small.volume}


def start_command(settings=Settings()):
    """One-shot test-only initialization hook; modeling runs in native callbacks."""
    module = runtime()
    original = module.Session.__init__

    def configured(session, command, custom=None):
        module.Session.__init__ = original
        original(session, command, custom)
        session.updating = True
        try:
            for key, options in (('execution', module.EXECUTIONS), ('result', module.RESULTS),
                                 ('direction', module.DIRECTIONS), ('extent', module.EXTENTS), ('start', module.STARTS)):
                index = next(i for i, (value, _) in enumerate(options) if value == getattr(settings, key))
                session.inputs[key].listItems.item(index).isSelected = True
            for key in ('distance', 'distance_two', 'offset'):
                session.inputs[key].expression = getattr(settings, key)
            for key in ('subtract', 'flipped'):
                session.inputs[key].value = getattr(settings, key)
        finally:
            session.updating = False
        session.sync()

    module.Session.__init__ = configured
    doc, design, root, region, originals = fixture('Ejix UI ' + settings.execution + ' ' + settings.result)
    selections = adsk.core.Application.get().userInterface.activeSelections
    selections.clear()
    selections.add(region.profiles.item(0))
    for body in originals:
        selections.add(body)
    adsk.core.Application.get().activeViewport.fit()
    assert adsk.core.Application.get().userInterface.commandDefinitions.itemById(module.COMMAND_ID).execute()
    return doc

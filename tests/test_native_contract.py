# SPDX-License-Identifier: GPL-3.0-only
"""Exercise production API-boundary code with small recording API doubles.

These are contract checks, not evidence of a running Fusion session.
"""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from Ejix.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'Ejix' / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Vec:
    """Minimal vector/point double for geometry probes."""
    def __init__(self, x=0., y=0., z=0.):
        self.x, self.y, self.z = x, y, z

    def copy(self):
        return Vec(self.x, self.y, self.z)

    def vectorTo(self, other):
        return Vec(other.x - self.x, other.y - self.y, other.z - self.z)

    def translateBy(self, other):
        self.x += other.x; self.y += other.y; self.z += other.z

    def normalize(self):
        return True

    def scaleBy(self, factor):
        self.x *= factor; self.y *= factor; self.z *= factor


def api_double():
    adsk, core, fusion = ModuleType('adsk'), ModuleType('adsk.core'), ModuleType('adsk.fusion')
    adsk.core, adsk.fusion = core, fusion
    for name in ('CommandEventHandler', 'InputChangedEventHandler', 'ValidateInputsEventHandler',
                 'CommandCreatedEventHandler', 'CustomEventHandler', 'ApplicationCommandEventHandler'):
        setattr(core, name, type(name, (), {}))
    core.ValueInput = NS(createByString=lambda expression: expression)
    class Collection(list):
        def add(self, item):
            self.append(item)
        @property
        def count(self):
            return len(self)
        def item(self, i):
            return self[i]
    core.ObjectCollection = Collection
    Collection.create = staticmethod(Collection)
    fusion.DistanceExtentDefinition = NS(create=lambda expression: ('distance', expression))
    fusion.ThroughAllExtentDefinition = NS(create=lambda: ('all',))
    fusion.OffsetStartDefinition = NS(create=lambda expression: ('offset', expression))
    fusion.ProfilePlaneStartDefinition = NS(create=lambda: ('profile',))
    fusion.FromEntityStartDefinition = NS(create=lambda entity, expression: ('object', entity, expression))
    fusion.ExtentDirections = NS(PositiveExtentDirection=1, NegativeExtentDirection=-1)
    fusion.FeatureOperations = NS(IntersectFeatureOperation='intersect', CutFeatureOperation='cut')
    fusion.FeatureHealthStates = NS(ErrorFeatureHealthState='error')
    fusion.PointContainment = NS(PointInsidePointContainment=0, PointOnPointContainment=1,
                                 PointOutsidePointContainment=2, UnknownPointContainment=3)
    fusion.ExtrudeFeature = type('ExtrudeFeature', (), {})
    fusion.ConstructionPlane = type('ConstructionPlane', (), {})
    fusion.CustomFeatureEventHandler = type('CustomFeatureEventHandler', (), {})
    core.Application = NS(get=Mock())
    fusion.CustomFeatureDefinition = NS(create=Mock())
    return adsk, core, fusion


class NativeBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        adsk, core, fusion = api_double()
        with patch.dict(sys.modules, {'adsk': adsk, 'adsk.core': core, 'adsk.fusion': fusion}):
            cls.adapter = load('Ejix._adapter_test', 'fusion_adapter.py')
            with patch.dict(sys.modules, {'Ejix.fusion_adapter': cls.adapter}):
                cls.command = load('Ejix._command_test', 'Ejix.py')
                cls.feature = load('Ejix._feature_test', 'feature.py')

    def test_missing_edit_command_does_not_create_a_persistent_definition(self):
        feature = self.feature
        feature._definition = feature._handler = None
        definitions = NS(itemById=Mock(return_value=None))
        with patch.object(feature.adsk.core.Application, 'get', return_value=NS(userInterface=NS(commandDefinitions=definitions))), \
             patch.object(feature.adsk.fusion.CustomFeatureDefinition, 'create') as create:
            with self.assertRaisesRegex(ValueError, 'Edit Eject'):
                feature.register()
        create.assert_not_called()
        self.assertIsNone(feature._definition)

    def test_eject_feature_option_has_no_badge_icon(self):
        items = NS(add=Mock())
        inputs = NS(addDropDownCommandInput=Mock(return_value=NS(listItems=items)))
        session = NS(inputs={})
        with patch.object(self.command.adsk.core, 'DropDownStyles', NS(LabeledIconDropDownStyle=1), create=True):
            self.command.Session.dropdown(session, inputs, 'execution', 'Timeline',
                                          self.command.EXECUTIONS, 'eject')
        self.assertEqual(items.add.call_args_list[1].args, ('Eject Feature', True, ''))

    def test_failed_registration_does_not_cache_a_partial_definition(self):
        feature = self.feature
        feature._definition = feature._handler = None
        definitions = NS(itemById=Mock(return_value=object()))
        candidate = NS(customFeatureCompute=NS(add=Mock(return_value=False)))
        with patch.object(feature.adsk.core.Application, 'get', return_value=NS(userInterface=NS(commandDefinitions=definitions))), \
             patch.object(feature.adsk.fusion.CustomFeatureDefinition, 'create', return_value=candidate):
            with self.assertRaises(ValueError):
                feature.register()
        self.assertIsNone(feature._definition)
        self.assertIsNone(feature._handler)

    def test_missing_profile_dependencies_recover_all_native_extrude_profiles(self):
        feature = self.feature
        first, second = NS(isValid=True, name='first'), NS(isValid=True, name='second')
        extrusion_type = feature.adsk.fusion.ExtrudeFeature
        first_extrude, second_extrude = extrusion_type(), extrusion_type()
        first_extrude.profile, second_extrude.profile = first, second
        dependencies = NS(itemById=lambda key: NS(entity=None) if key in ('source0', 'source1') else None)
        custom = NS(dependencies=dependencies, features=[first_extrude, first_extrude, second_extrude])
        self.assertEqual(feature.sources(custom), [first, second])

    def test_native_all_uses_through_all_definition(self):
        from dataclasses import replace
        extrude = Mock()
        self.adapter.apply_extent(extrude, replace(Settings(), extent='all', flipped=True))
        extrude.setOneSideExtent.assert_called_once_with(('all',), -1, '0 deg')

    def test_two_sides_preserve_independent_expressions(self):
        from dataclasses import replace
        extrude = Mock()
        self.adapter.apply_extent(extrude, replace(Settings(), direction='two', distance='Width / 2', distance_two='Gap'))
        extrude.setTwoSidesExtent.assert_called_once_with(('distance', 'Width / 2'), ('distance', 'Gap'), '0 deg', '0 deg')

    def test_symmetric_arrow_uses_half_length(self):
        from dataclasses import replace
        extrude = Mock()
        self.adapter.apply_extent(extrude, replace(Settings(), direction='symmetric', distance='12 mm'))
        extrude.setSymmetricExtent.assert_called_once_with('12 mm', False, '0 deg')

    def test_signed_start_offset_preserved(self):
        from dataclasses import replace
        extrude = Mock()
        self.adapter.apply_extent(extrude, replace(Settings(), start='offset', offset='-Offset'))
        self.assertEqual(extrude.startExtent, ('offset', '-Offset'))

    def test_profile_plane_ignores_hidden_offset(self):
        extrude = Mock()
        self.adapter.apply_extent(extrude, Settings(offset='StaleParameter'))
        self.assertEqual(extrude.startExtent, ('profile',))

    def test_from_object_preserves_entity_and_signed_offset(self):
        extrude = Mock()
        entity = NS(nativeObject=None)
        self.adapter.apply_extent(extrude, Settings(start='object', offset='-2 mm'), (None, None, entity))
        self.assertEqual(extrude.startExtent, ('object', entity, '-2 mm'))

    def test_status_changes_do_not_reenter_preview(self):
        s = NS(updating=False, sync=Mock(), refresh=Mock())
        self.command.Changed(s).notify(NS(input=NS(id='status')))
        s.refresh.assert_not_called()

    def test_activation_leaves_graphics_to_preview_transaction(self):
        s = NS(seeded=False, updating=False, custom=True, sync=Mock(),
               refresh=Mock(), command=NS(beginStep=Mock()))
        self.command.Activated(s).notify(NS())
        s.command.beginStep.assert_called_once()
        s.refresh.assert_called_once_with(draw=False)

    def test_preview_and_execution_exclude_the_same_whole_bodies(self):
        partial = NS(original_volume=64, extracted_volume=12)
        whole = NS(original_volume=1, extracted_volume=1)
        s = NS(custom=None, hits=(partial, whole), object_rows=[NS(value=True), NS(value=True)], settings=Settings)
        self.assertEqual(self.command.Session.active_hits(s), (partial,))
        s.settings = lambda: Settings(subtract=False)
        self.assertEqual(self.command.Session.active_hits(s), (partial, whole))

    def test_status_is_written_before_asm_graphics_are_created(self):
        events = []
        hits = (NS(original_volume=64, extracted_volume=16),)
        s = NS(renderer=NS(clear=lambda: events.append('clear'),
                           show=lambda *args: events.append('draw')),
               error='', profiles=lambda: ['profile'], settings=Settings,
               custom=None, design=object(), targets=lambda: (),
               analysis=NS(analyze=lambda *args: hits), auto_direction=False,
               update_objects=lambda: None, active_hits=lambda: hits,
               inputs={'preview': NS(value=True)}, status=lambda text: events.append('status'))
        self.command.Session.refresh(s)
        self.assertEqual(events, ['clear', 'status', 'draw'])

    def test_preview_draws_ordered_parts_not_the_unioned_body(self):
        combined = NS(body='included', original_volume=10, extracted_volume=6)
        first = NS(body='included', extracted_volume=4)
        second = NS(body='included', extracted_volume=2)
        excluded = NS(body='excluded', extracted_volume=1)
        show = Mock()
        s = NS(renderer=NS(clear=Mock(), show=show), error='', profiles=lambda: ['profile'],
               settings=Settings, custom=None, design=object(), targets=lambda: (),
               analysis=NS(analyze=lambda *args: (combined,), group_hits=[(first, excluded), (second,)]),
               auto_direction=False, update_objects=Mock(), active_hits=lambda: (combined,),
               inputs={'preview': NS(value=True)}, status=Mock())
        self.command.Session.refresh(s)
        self.assertEqual(show.call_args.args[1], (first, second))

    def test_profile_results_and_order_note_follow_selection_and_mode(self):
        keys = ('flipped', 'distance', 'start_object', 'offset', 'distance_two', 'target',
                'target_two', 'object_offset', 'object_offset_two', 'region_mode', 'region_note')
        inputs = {key: NS(isVisible=False) for key in keys}
        session = NS(inputs=inputs, profiles=lambda: ['first', 'second'], settings=Settings)
        self.command.Session.sync(session, position=False)
        self.assertTrue(inputs['region_mode'].isVisible)
        self.assertTrue(inputs['region_note'].isVisible)
        session.settings = lambda: Settings(region_mode='combined')
        self.command.Session.sync(session, position=False)
        self.assertTrue(inputs['region_mode'].isVisible)
        self.assertFalse(inputs['region_note'].isVisible)
        session.profiles = lambda: ['first']
        self.command.Session.sync(session, position=False)
        self.assertFalse(inputs['region_mode'].isVisible)
        self.assertFalse(inputs['region_note'].isVisible)

    def test_group_preview_intersects_the_remaining_source_for_each_plane(self):
        preview = self.command.preview
        class Shape:
            def __init__(self, cells): self.cells = set(cells)
            @property
            def volume(self): return len(self.cells)
            @property
            def isSolid(self): return bool(self.cells)
        class Manager:
            def copy(self, shape): return Shape(shape.cells)
            def booleanOperation(self, left, right, operation):
                if operation == 'union': left.cells |= right.cells
                elif operation == 'difference': left.cells -= right.cells
                return True
        class Analysis:
            def analyze(self, design, group, settings, targets, objects):
                return tuple(preview.Hit(body, Shape(shape.cells & group[0]), shape.volume,
                                         len(shape.cells & group[0]))
                             for body, shape in objects if shape.cells & group[0])
        manager = Manager()
        original = Shape(range(10))
        with patch.object(preview, 'profile_groups', return_value=[[{1, 2, 3, 4}], [{3, 4, 5, 6}]]), \
             patch.object(preview.adapter, 'validate'), patch.object(preview, 'Analysis', Analysis), \
             patch.object(preview.adsk.fusion, 'TemporaryBRepManager', NS(get=lambda: manager), create=True), \
             patch.object(preview.adsk.fusion, 'BooleanTypes', NS(UnionBooleanType='union', DifferenceBooleanType='difference'), create=True):
            analysis = preview.GroupAnalysis()
            combined = analysis.analyze(None, ['a', 'b'], Settings(), objects=[('body', original)])
        self.assertEqual([group[0].volume.cells for group in analysis.group_hits], [{1, 2, 3, 4}, {5, 6}])
        self.assertEqual(combined[0].volume.cells, {1, 2, 3, 4, 5, 6})
        self.assertEqual(original.cells, set(range(10)))

    def test_failed_extent_reports_error(self):
        extrude = Mock()
        extrude.setOneSideExtent.return_value = False
        with self.assertRaisesRegex(ValueError, 'extent'):
            self.adapter.apply_extent(extrude, Settings())

    def test_existing_extrude_receives_explicit_zero_taper(self):
        class ExistingExtrude:
            def setOneSideExtent(self, extent, direction, taper=None):
                if taper is None:
                    raise RuntimeError('3 : invalid argument taperAngle')
                return True
        self.adapter.apply_extent(ExistingExtrude(), Settings())

    def test_existing_intersect_keeps_its_copied_participant(self):
        copied = object()
        class ExistingExtrude(self.adapter.adsk.fusion.ExtrudeFeature):
            participantBodies = [copied]
            def setOneSideExtent(self, *args):
                self.participantBodies = ['automatically discovered original']
                return True
        extrude = ExistingExtrude()
        self.adapter.apply_extent(extrude, Settings())
        self.assertEqual(extrude.participantBodies, [copied])

    def test_ignored_feature_can_resume_without_losing_its_participant(self):
        copied = object()
        class Extrusion:
            isSuppressed = False
            healthState = 'healthy'
            timelineObject = NS(rollTo=lambda before: True)
            participantBodies = [copied]
            _operation = 'intersect'
            @property
            def operation(self):
                return self._operation
            @operation.setter
            def operation(self, value):
                self._operation = value
                self.participantBodies = ['autodetected original']
        extrusion = Extrusion()
        copy = NS(isSuppressed=False, healthState='healthy')
        cut = NS(isSuppressed=False, healthState='healthy', timelineObject=NS(rollTo=lambda before: True))
        owned = [copy, extrusion, cut]
        def verify_participants(*args):
            self.assertEqual(extrusion.participantBodies, [copied])
        with patch.object(self.feature, 'apply_extent', side_effect=verify_participants):
            self.feature.edit_graph(owned, [[0, 1, 2]], [extrusion], Settings(), (), [True])
            self.assertTrue(cut.isSuppressed)
            self.assertFalse(copy.isSuppressed)
            self.assertEqual(extrusion.operation, 'cut')
            self.feature.edit_graph(owned, [[0, 1, 2]], [extrusion], Settings(), (), [False])
        self.assertFalse(cut.isSuppressed)
        self.assertEqual(extrusion.operation, 'intersect')

    def test_source_groups_include_hidden_base_features(self):
        fusion = self.feature.adsk.fusion
        first, second = fusion.ExtrudeFeature(), fusion.ExtrudeFeature()
        first.objectType = second.objectType = 'adsk::fusion::ExtrudeFeature'
        class Cut:
            objectType = 'adsk::fusion::CombineFeature'
        owned = [NS(objectType='adsk::fusion::CopyPasteBody'), NS(objectType='adsk::fusion::BaseFeature'), first,
                 NS(objectType='adsk::fusion::CopyPasteBody'), NS(objectType='adsk::fusion::BaseFeature'), second,
                 Cut(), Cut()]
        # Legacy timeline indices omit hidden BaseFeatures; they are not array
        # indices into CustomFeature.features and must be migrated.
        custom = NS(customNamedValues=NS(value=lambda key: {
            'ejix_nodes': '[[0,1,4],[2,3,5]]', 'ejix_results': '[["first"],["second"]]'}.get(key)))
        with patch.object(fusion, 'CombineFeature', Cut, create=True):
            groups = self.feature.node_groups(custom, owned, [first, second])
        self.assertEqual(groups, [[0, 1, 2, 6], [3, 4, 5, 7]])

    def test_restored_results_refresh_body_tokens_and_exclude_empty_bodies(self):
        original = NS(isValid=True, isSolid=True, volume=64, entityToken='original')
        empty = NS(isValid=True, isSolid=True, volume=0, entityToken='empty')
        restored = NS(isValid=True, isSolid=True, volume=.25, entityToken='restored')
        save = Mock()
        custom = NS(customNamedValues=NS(value=lambda key: '[["old"]]', addOrSetValue=save))
        with patch.object(self.feature, 'original_bodies', return_value=[original]), \
             patch.object(self.feature, 'sources', return_value=[]):
            self.feature.capture_results(custom, [NS(bodies=[original, empty, restored])], [False])
        save.assert_called_once_with('ejix_results', '[["restored"]]')

    def test_construction_plane_owner_uses_component(self):
        entity = self.adapter.adsk.fusion.ConstructionPlane()
        entity.nativeObject = None
        entity.component = object()
        with patch.object(self.adapter.adsk.fusion, 'Profile', type('Profile', (), {}), create=True), \
             patch.object(self.adapter.adsk.fusion, 'BRepFace', type('BRepFace', (), {}), create=True), \
             patch.object(self.adapter.adsk.fusion, 'BRepBody', type('BRepBody', (), {}), create=True):
            self.assertIs(self.adapter.owner(entity), entity.component)

    def test_face_plane_uses_topological_normal_for_reversed_faces(self):
        class Face:
            nativeObject = None
            isParamReversed = True
        class Plane:
            pass
        normal = Mock()
        face = Face()
        face.geometry = Plane()
        face.geometry.origin = object()
        face.geometry.normal = NS(copy=lambda: normal)
        with patch.object(self.adapter.adsk.fusion, 'Profile', type('Profile', (), {}), create=True), \
             patch.object(self.adapter.adsk.fusion, 'BRepFace', Face, create=True), \
             patch.object(self.adapter.adsk.core, 'Plane', Plane, create=True):
            origin, direction = self.adapter.plane(face)
        self.assertIs(direction, normal)
        normal.scaleBy.assert_called_once_with(-1)

    def test_discovery_ignores_empty_persistent_body_placeholders(self):
        solid = NS(isSolid=True, isVisible=True, volume=1)
        empty = NS(isSolid=True, isVisible=True, volume=0)
        with patch.object(self.adapter, 'owner', return_value=NS(bRepBodies=[solid, empty])):
            self.assertEqual(self.adapter.candidate_bodies([NS()]), [solid])

    def test_native_finish_groups_only_the_created_span(self):
        backend = self.adapter.Backend.__new__(self.adapter.Backend)
        group = NS(name='', isCollapsed=False)
        add = Mock(return_value=group)
        backend.design = NS(timeline=NS(timelineGroups=NS(add=add)))
        backend.first = NS(timelineObject=NS(index=5))
        backend.last = NS(timelineObject=NS(index=10))
        self.assertIsNone(backend.finish(Settings(execution='native')))
        add.assert_called_once_with(5, 10)
        self.assertEqual(group.name, 'Eject')
        self.assertTrue(group.isCollapsed)

    def test_cut_keeps_all_extracted_tools(self):
        data = NS()
        source = NS(nativeObject=None, isValid=True, isSolid=True)
        cut = NS(healthState='healthy', name='', bodies=[source])
        combines = NS(createInput=Mock(return_value=data), add=Mock(return_value=cut))
        backend = self.adapter.Backend.__new__(self.adapter.Backend)
        backend.component = NS(features=NS(combineFeatures=combines))
        backend.created, backend.first, backend.last = [], None, None
        backend.extra_nodes = []
        backend.source_fragments = []
        backend.design = NS(timeline=NS(markerPosition=0))
        backend.originals, backend.source_nodes = [source], [[]]
        tools = [object(), object(), object()]
        backend.subtract(source, tools)
        self.assertTrue(data.isKeepToolBodies)
        self.assertEqual(list(combines.createInput.call_args.args[1]), tools)
        self.assertIs(combines.createInput.call_args.args[0], source)

    def test_intersect_participates_only_on_copy_and_preserves_split_outputs(self):
        copied = object()
        source = NS(nativeObject=None, name='Original')
        profile = NS(nativeObject=None)
        copy_feature = NS(healthState='healthy', name='', bodies=NS(count=1, item=lambda i: copied))
        copy_feature.timelineObject = NS(index=0)
        pieces = [NS(name='', isVisible=False), NS(name='', isVisible=False)]
        intersection = NS(healthState='healthy', name='', bodies=pieces)
        intersection.timelineObject = NS(index=1)
        definition = Mock()
        extrudes = NS(createInput=Mock(return_value=definition), add=Mock(return_value=intersection))
        copies = NS(add=Mock(return_value=copy_feature))
        backend = self.adapter.Backend.__new__(self.adapter.Backend)
        backend.component = NS(features=NS(copyPasteBodies=copies, extrudeFeatures=extrudes))
        backend.component.bRepBodies = [source]
        backend.created, backend.extrudes = [], []
        backend.originals, backend.result_groups, backend.targets = [], [], ()
        backend.profiles = ()
        backend.source_nodes = []
        backend.first = backend.last = None
        result = backend.extract(source, [profile], Settings())
        self.assertEqual(definition.participantBodies, [copied])
        self.assertNotIn(source, definition.participantBodies)
        self.assertEqual(result, tuple(pieces))
        self.assertTrue(all(piece.isVisible for piece in pieces))

    def test_prior_region_can_split_copy_before_next_intersection(self):
        source = NS(nativeObject=None, name='Original', isValid=True, isSolid=True)
        previous = NS(name='Previous', isValid=True, isSolid=True)
        copied = NS(name='Copy', isValid=True, isSolid=True)
        fragment = NS(name='Copy fragment', isValid=True, isSolid=True)
        copy_feature = NS(healthState='healthy', name='', bodies=NS(count=1, item=lambda i: copied),
                          timelineObject=NS(index=0))
        cut = NS(healthState='healthy', name='', bodies=[copied, fragment, previous], timelineObject=NS(index=1))
        intersection = NS(healthState='healthy', name='', bodies=[copied, fragment], timelineObject=NS(index=2))
        cut_input, intersect_input = Mock(), Mock()
        backend = self.adapter.Backend.__new__(self.adapter.Backend)
        backend.component = NS(bRepBodies=[source, previous], features=NS(
            copyPasteBodies=NS(add=Mock(return_value=copy_feature)),
            combineFeatures=NS(createInput=Mock(return_value=cut_input), add=Mock(return_value=cut)),
            extrudeFeatures=NS(createInput=Mock(return_value=intersect_input), add=Mock(return_value=intersection))))
        backend.created, backend.extrudes, backend.originals, backend.result_groups = [], [], [], []
        backend.profiles, backend.targets, backend.first, backend.last = (), (), None, None
        backend.design = object()
        backend.analysis = NS(analyze=Mock(return_value=[object()]))
        result = backend.extract(source, [NS(nativeObject=None)], Settings(), excluded=(previous,))
        self.assertEqual(intersect_input.participantBodies, [copied, fragment])
        self.assertEqual(result, (copied, fragment))
        self.assertTrue(cut_input.isKeepToolBodies)

    def test_nonintersecting_copy_fragment_is_removed_before_extrusion(self):
        source = NS(nativeObject=None, name='Original', isValid=True, isSolid=True)
        previous = NS(name='Previous', isValid=True, isSolid=True)
        hit = NS(name='Hit', isValid=True, isSolid=True)
        miss = NS(name='Miss', isValid=True, isSolid=True)
        copy = NS(healthState='healthy', name='', bodies=NS(count=1, item=lambda i: hit), timelineObject=NS(index=0))
        cut = NS(healthState='healthy', name='', bodies=[hit, miss, previous], timelineObject=NS(index=1))
        removed = NS(healthState='healthy', name='', timelineObject=NS(index=2))
        extrusion = NS(healthState='healthy', name='', bodies=[hit], timelineObject=NS(index=3))
        cut_input, intersect_input = Mock(), Mock()
        removals = NS(add=Mock(return_value=removed))
        backend = self.adapter.Backend.__new__(self.adapter.Backend)
        backend.component = NS(bRepBodies=[source, previous], features=NS(
            copyPasteBodies=NS(add=Mock(return_value=copy)), removeFeatures=removals,
            combineFeatures=NS(createInput=Mock(return_value=cut_input), add=Mock(return_value=cut)),
            extrudeFeatures=NS(createInput=Mock(return_value=intersect_input), add=Mock(return_value=extrusion))))
        backend.created, backend.extrudes, backend.originals, backend.result_groups = [], [], [], []
        backend.profiles, backend.targets, backend.first, backend.last = (), (), None, None
        backend.design = object()
        backend.analysis = NS(analyze=Mock(side_effect=[[object()], []]))
        result = backend.extract(source, [NS(nativeObject=None)], Settings(), excluded=(previous,))
        removals.add.assert_called_once_with(miss)
        self.assertEqual(intersect_input.participantBodies, [hit])
        self.assertEqual(result, (hit,))

    def test_face_owner_reported_by_intersect_is_not_an_extracted_result(self):
        source = NS(nativeObject=None, name='Original', isVisible=True)
        copied = NS(nativeObject=None, name='Copy', isVisible=False)
        copied_feature = NS(healthState='healthy', bodies=NS(count=1, item=lambda i: copied), name='')
        intersection = NS(healthState='healthy', bodies=[copied, source], name='')
        copied_feature.timelineObject, intersection.timelineObject = NS(index=0), NS(index=1)
        definition = Mock()
        backend = self.adapter.Backend.__new__(self.adapter.Backend)
        backend.component = NS(bRepBodies=[source], features=NS(
            copyPasteBodies=NS(add=Mock(return_value=copied_feature)),
            extrudeFeatures=NS(createInput=Mock(return_value=definition), add=Mock(return_value=intersection))))
        backend.created, backend.extrudes, backend.originals, backend.result_groups = [], [], [], []
        backend.source_nodes = []
        backend.first = backend.last = None
        backend.targets = ()
        backend.profiles = ()
        result = backend.extract(source, [NS(nativeObject=None)], Settings())
        self.assertEqual(result, (copied,))
        self.assertEqual(source.name, 'Original')

    def test_failed_native_feature_is_journaled_before_health_check(self):
        backend = self.adapter.Backend.__new__(self.adapter.Backend)
        backend.created = []
        failed = NS(healthState='error', errorOrWarningMessage='no intersection')
        with self.assertRaisesRegex(ValueError, 'no intersection'):
            backend.track(failed, 'Ejix Intersect')
        self.assertEqual(backend.created, [failed])

    def test_abort_removes_features_in_reverse_dependency_order(self):
        deleted = []
        def item(name):
            return NS(name=name, isValid=True, deleteMe=lambda: deleted.append(name) or True)
        backend = self.adapter.Backend.__new__(self.adapter.Backend)
        backend.created = [item('copy'), item('intersect'), item('cut')]
        backend.custom, backend.marker = None, 4
        backend.design = NS(timeline=NS(markerPosition=9, count=4))
        backend.abort()
        self.assertEqual(deleted, ['cut', 'intersect', 'copy'])
        self.assertEqual(backend.design.timeline.markerPosition, 4)

    def session(self):
        return NS(inputs={'preview': NS(value=True)}, custom=None, updating=False, error='',
                  preview_valid=False, preview_key=None, status=Mock(),
                  refresh=Mock(), renderer=NS(clear=Mock()), targets=lambda: (),
                  check=Mock(return_value=(Settings(), object(), ['profile'], ['body'])))

    def test_graphics_preview_does_not_invoke_the_modeling_backend(self):
        s = self.session()
        args = NS()
        with patch.object(self.command.adapter, 'Backend') as backend, \
             patch.object(self.command.engine, 'eject') as eject:
            self.command.Previewed(s).notify(args)
        backend.assert_not_called()
        eject.assert_not_called()
        s.refresh.assert_called_once()
        self.assertFalse(args.isValidResult)
        self.assertFalse(hasattr(args, 'executeFailed'))

    def test_final_execute_failure_asks_fusion_to_abort_transaction(self):
        s = self.session()
        args = NS()
        with patch.object(self.command.adapter, 'Backend', return_value=NS()), \
             patch.object(self.command.engine, 'eject', side_effect=ValueError('bad intersection')):
            self.command.Executed(s).notify(args)
        self.assertTrue(args.executeFailed)
        self.assertIn('bad intersection', args.executeFailedMessage)

    def test_graphics_preview_requires_modeling_on_ok(self):
        s = self.session()
        args = NS()
        with patch.object(self.command.adapter, 'Backend', return_value=NS()), \
             patch.object(self.command.engine, 'eject', return_value=NS(bodies=[1, 2])) as build:
            self.command.Previewed(s).notify(args)
        self.assertFalse(args.isValidResult)
        build.assert_not_called()

    def test_distance_drag_does_not_reset_manipulator(self):
        s = NS(updating=False, custom=None, sync=Mock(), refresh=Mock())
        self.command.Changed(s).notify(NS(input=NS(id='distance')))
        s.sync.assert_called_once_with(position=False)
        s.refresh.assert_called_once_with(draw=False)

    @staticmethod
    def distance_control(expression, value):
        return NS(expression=expression, isValidExpression=True, value=value,
                  hasMinimumValue=True, minimumValue=0., isMinimumValueInclusive=True)

    def test_manipulator_drag_uses_live_value_not_stale_expression(self):
        units = NS(evaluateExpression=lambda expression, unit: 3.9)
        control = self.distance_control('39 mm', 5.)
        self.assertEqual(self.command.length_expression(control, units), '5 cm')

    def test_typed_zero_distance_keeps_the_committed_zero(self):
        units = NS(evaluateExpression=lambda expression, unit: 0.)
        control = self.distance_control('0 mm', 0.)
        self.assertEqual(self.command.length_expression(control, units), '0 mm')

    def test_drag_starting_from_zero_uses_the_live_value(self):
        units = NS(evaluateExpression=lambda expression, unit: 0.)
        control = self.distance_control('0 mm', 5.)
        self.assertEqual(self.command.length_expression(control, units), '5 cm')

    def test_matching_expression_is_kept_for_parameters(self):
        units = NS(evaluateExpression=lambda expression, unit: 3.9)
        control = NS(expression='Width / 2', isValidExpression=True, value=3.9)
        self.assertEqual(self.command.length_expression(control, units), 'Width / 2')

    def test_invalid_expression_is_not_replaced_by_stale_value(self):
        units = NS(evaluateExpression=Mock())
        control = NS(expression='Width /', isValidExpression=False, value=3.9)
        self.assertEqual(self.command.length_expression(control, units), 'Width /')
        units.evaluateExpression.assert_not_called()

    def test_settings_read_live_value_for_dragged_distance_only(self):
        inputs = {key: NS(selectedItem=NS(index=0))
                  for key in ('execution', 'result', 'start', 'direction', 'extent')}
        inputs.update({
            'subtract': NS(value=True), 'flipped': NS(value=False),
            'distance': NS(expression='39 mm', isValidExpression=True, value=5.),
            'distance_two': NS(expression='10 mm', isValidExpression=True, value=1.),
            'offset': NS(expression='0 mm', isValidExpression=True, value=0.),
            'object_offset': NS(expression='0 mm', isValidExpression=True, value=0.),
            'object_offset_two': NS(expression='0 mm', isValidExpression=True, value=0.)})
        values = {'39 mm': 3.9, '10 mm': 1., '0 mm': 0.}
        units = NS(evaluateExpression=lambda expression, unit: values[expression])
        session = NS(inputs=inputs, design=NS(unitsManager=units))
        session.choice = lambda key, options: self.command.Session.choice(session, key, options)
        settings = self.command.Session.settings(session)
        self.assertEqual(settings.distance, '5 cm')
        self.assertEqual(settings.distance_two, '10 mm')
        self.assertEqual(settings.offset, '0 mm')

    def test_settings_keep_typed_zero_distance(self):
        inputs = {key: NS(selectedItem=NS(index=0))
                  for key in ('execution', 'result', 'start', 'direction', 'extent')}
        inputs.update({
            'subtract': NS(value=True), 'flipped': NS(value=False),
            'distance': NS(expression='0 mm', isValidExpression=True, value=0., hasMinimumValue=True,
                           minimumValue=0., isMinimumValueInclusive=True),
            'distance_two': NS(expression='10 mm', isValidExpression=True, value=1.),
            'offset': NS(expression='0 mm', isValidExpression=True, value=0.),
            'object_offset': NS(expression='0 mm', isValidExpression=True, value=0.),
            'object_offset_two': NS(expression='0 mm', isValidExpression=True, value=0.)})
        values = {'0 mm': 0., '10 mm': 1.}
        units = NS(evaluateExpression=lambda expression, unit: values[expression])
        session = NS(inputs=inputs, design=NS(unitsManager=units))
        session.choice = lambda key, options: self.command.Session.choice(session, key, options)
        self.assertEqual(self.command.Session.settings(session).distance, '0 mm')

    def test_negative_one_side_distance_reverses_effective_direction(self):
        inputs = {key: NS(selectedItem=NS(index=0))
                  for key in ('execution', 'result', 'start', 'direction', 'extent')}
        inputs.update({key: NS(expression='0 mm', isValidExpression=True, value=0.)
                       for key in ('distance_two', 'offset', 'object_offset', 'object_offset_two')})
        inputs.update({'subtract': NS(value=True), 'flipped': NS(value=False),
                       'distance': NS(expression='-Width', isValidExpression=True, value=-2.)})
        units = NS(evaluateExpression=lambda expression, unit: -2. if expression == '-Width' else 0.)
        session = NS(inputs=inputs, design=NS(unitsManager=units))
        session.choice = lambda key, options: self.command.Session.choice(session, key, options)
        settings = self.command.Session.settings(session)
        self.assertTrue(settings.flipped)
        self.assertEqual(settings.distance, '-(-Width)')
        inputs['flipped'].value = True
        self.assertFalse(self.command.Session.settings(session).flipped)

    def test_sketch_on_face_flips_an_outward_sketch_normal_inward(self):
        profile = NS(nativeObject=None)
        normal = Mock()
        normal.dotProduct.return_value = 1.
        session = NS(custom=None, updating=False, oriented=None, inputs={'flipped': NS(value=False)},
                     profiles=lambda: [profile])
        with patch.object(self.command.adapter, 'support_normal', return_value=object()), \
             patch.object(self.command.adapter, 'plane', return_value=(None, normal)):
            self.command.Session.orient_inward(session)
        self.assertTrue(session.inputs['flipped'].value)
        normal.normalize.assert_called_once_with()

    def test_sketch_on_face_keeps_an_inward_sketch_normal(self):
        normal = Mock()
        normal.dotProduct.return_value = -1.
        session = NS(custom=None, updating=False, oriented=None, inputs={'flipped': NS(value=False)},
                     profiles=lambda: [NS(nativeObject=None)])
        with patch.object(self.command.adapter, 'support_normal', return_value=object()), \
             patch.object(self.command.adapter, 'plane', return_value=(None, normal)):
            self.command.Session.orient_inward(session)
        self.assertFalse(session.inputs['flipped'].value)

    def test_reselecting_the_same_profile_keeps_a_manual_flip(self):
        profile = NS(nativeObject=None)
        session = NS(custom=None, updating=False, oriented=profile, inputs={'flipped': NS(value=True)},
                     profiles=lambda: [profile])
        with patch.object(self.command.adapter, 'support_normal') as support:
            self.command.Session.orient_inward(session)
        support.assert_not_called()
        self.assertTrue(session.inputs['flipped'].value)

    def test_profile_without_a_support_face_keeps_the_flip(self):
        session = NS(custom=None, updating=False, oriented=None, inputs={'flipped': NS(value=False)},
                     profiles=lambda: [NS(nativeObject=None)])
        with patch.object(self.command.adapter, 'support_normal', return_value=None):
            self.command.Session.orient_inward(session)
        self.assertFalse(session.inputs['flipped'].value)

    def test_edit_keeps_the_saved_flip_direction(self):
        control = NS(value=True)
        session = NS(custom=object(), updating=False, oriented=None, inputs={'flipped': control},
                     profiles=lambda: [object()])
        with patch.object(self.command.adapter, 'support_normal') as support:
            self.command.Session.orient_inward(session)
        support.assert_not_called()
        self.assertTrue(control.value)

    def test_support_normal_uses_the_solid_face_direction(self):
        class Profile:
            pass
        class Plane:
            pass
        class Body:
            isSolid = True
        class Face:
            nativeObject = None
            isParamReversed = True
            body = Body()
        normal = Mock()
        face = Face()
        face.geometry = Plane()
        face.geometry.normal = NS(copy=lambda: normal)
        profile = Profile()
        profile.nativeObject = None
        profile.parentSketch = NS(isParametric=True, referencePlane=face)
        with patch.object(self.adapter.adsk.fusion, 'Profile', Profile, create=True), \
             patch.object(self.adapter.adsk.fusion, 'BRepFace', Face, create=True), \
             patch.object(self.adapter.adsk.fusion, 'BRepBody', Body, create=True), \
             patch.object(self.adapter.adsk.core, 'Plane', Plane, create=True):
            direction = self.adapter.support_normal(profile)
        self.assertIs(direction, normal)
        normal.scaleBy.assert_called_once_with(-1)
        normal.normalize.assert_called_once_with()

    def test_support_normal_recovers_a_face_blocked_by_the_timeline(self):
        class Plane:
            pass
        class Profile:
            pass
        class Body:
            isSolid = True
            volume = 8.
            faces = []
            @staticmethod
            def pointContainment(point):
                return 0 if point.z < 0 else 2
        class Face:
            nativeObject = None
            isParamReversed = False
            isPointOnFace = Mock(return_value=True)
        class Sketch:
            isParametric = True
            @property
            def referencePlane(self):
                raise RuntimeError('need to roll timeline back before sketch')
            def sketchToModelSpace(self, point):
                return Vec()
        body, face = Body(), Face()
        face.geometry = Plane()
        face.geometry.normal = Vec(0., 0., 1.)
        face.body = body
        body.faces = [face]
        sketch = Sketch()
        sketch.parentComponent = NS(bRepBodies=[body])
        profile = Profile()
        profile.nativeObject = None
        profile.parentSketch = sketch
        profile.areaProperties = lambda: NS(centroid=Vec())
        with patch.object(self.adapter.adsk.fusion, 'Profile', Profile, create=True), \
             patch.object(self.adapter.adsk.fusion, 'BRepFace', Face, create=True), \
             patch.object(self.adapter.adsk.fusion, 'BRepBody', Body, create=True), \
             patch.object(self.adapter.adsk.core, 'Plane', Plane, create=True), \
             patch.object(self.adapter.adsk.core, 'Vector3D', NS(create=Vec), create=True), \
             patch.object(self.adapter.adsk.core.Application, 'get',
                          return_value=NS(pointTolerance=1e-5)):
            direction = self.adapter.support_normal(profile)
        self.assertEqual(direction.z, 1.)
        self.assertEqual(face.isPointOnFace.call_count, 1)

    def test_support_normal_infers_material_side_when_the_face_is_gone(self):
        class Profile:
            pass
        class Body:
            isSolid = True
            volume = 8.
            @staticmethod
            def pointContainment(point):
                return 0 if point.z > 0 else 2
        class Face:
            nativeObject = None
            isParamReversed = False
            isPointOnFace = Mock(return_value=False)
        class Sketch:
            isParametric = True
            @property
            def referencePlane(self):
                raise RuntimeError('need to roll timeline back before sketch')
            def sketchToModelSpace(self, point):
                return Vec()
        body, face = Body(), Face()
        face.geometry = object()
        body.faces = [face]
        sketch = Sketch()
        sketch.parentComponent = NS(bRepBodies=[body])
        profile = Profile()
        profile.nativeObject = None
        profile.parentSketch = sketch
        profile.areaProperties = lambda: NS(centroid=Vec())
        direction = Vec(0., 0., 1.)
        with patch.object(self.adapter, 'plane', return_value=(None, direction)), \
             patch.object(self.adapter.adsk.fusion, 'Profile', Profile, create=True), \
             patch.object(self.adapter.adsk.fusion, 'BRepBody', Body, create=True), \
             patch.object(self.adapter.adsk.core, 'Plane', type('Plane', (), {}), create=True), \
             patch.object(self.adapter.adsk.core, 'Vector3D', NS(create=Vec), create=True), \
             patch.object(self.adapter.adsk.core.Application, 'get',
                          return_value=NS(pointTolerance=1e-5)):
            result = self.adapter.support_normal(profile)
        self.assertIs(result, direction)
        self.assertEqual(result.z, -1.)

    def test_support_normal_stays_unknown_without_material_on_either_side(self):
        class Profile:
            pass
        class Body:
            isSolid = True
            volume = 8.
            faces = []
            @staticmethod
            def pointContainment(point):
                return 2
        class Sketch:
            isParametric = True
            @property
            def referencePlane(self):
                raise RuntimeError('need to roll timeline back before sketch')
            def sketchToModelSpace(self, point):
                return Vec()
        body = Body()
        sketch = Sketch()
        sketch.parentComponent = NS(bRepBodies=[body])
        profile = Profile()
        profile.nativeObject = None
        profile.parentSketch = sketch
        profile.areaProperties = lambda: NS(centroid=Vec())
        direction = Vec(0., 0., 1.)
        with patch.object(self.adapter, 'plane', return_value=(None, direction)), \
             patch.object(self.adapter.adsk.fusion, 'Profile', Profile, create=True), \
             patch.object(self.adapter.adsk.fusion, 'BRepBody', Body, create=True), \
             patch.object(self.adapter.adsk.core, 'Plane', type('Plane', (), {}), create=True), \
             patch.object(self.adapter.adsk.core, 'Vector3D', NS(create=Vec), create=True), \
             patch.object(self.adapter.adsk.core.Application, 'get',
                          return_value=NS(pointTolerance=1e-5)):
            self.assertIsNone(self.adapter.support_normal(profile))

    def test_support_normal_ignores_sketches_without_a_solid_face(self):
        with patch.object(self.adapter.adsk.fusion, 'Profile', type('Profile', (), {}), create=True):
            self.assertIsNone(self.adapter.support_normal(NS(nativeObject=None)))

    def test_preview_color_is_a_golden_show_through_effect(self):
        # Strict slots catch unsupported API attributes: SWIG otherwise silently
        # accepts Python-only fields such as the nonexistent body.showThrough.
        class Graphic:
            __slots__ = ('isSelectable', 'color', 'depthPriority', 'opacity')

            def setOpacity(self, value, override):
                self.opacity = (value, override)
                return True

        graphic = Graphic()
        group = NS(isSelectable=True, addBRepBody=Mock(return_value=graphic))
        design = NS(rootComponent=NS(customGraphicsGroups=NS(add=Mock(return_value=group))))
        module = self.command.preview
        effect = NS(create=lambda color, opacity: NS(kind='show-through', color=color, opacity=opacity))
        manager = NS(copy=lambda body: body)
        with patch.object(module.adsk.core, 'Color', NS(create=lambda *rgb: rgb), create=True), \
             patch.object(module.adsk.fusion, 'CustomGraphicsShowThroughColorEffect', effect, create=True), \
             patch.object(module.adsk.fusion, 'TemporaryBRepManager', NS(get=lambda: manager), create=True):
            module.Renderer().show(design, [NS(volume=object())], [NS(assemblyContext=None)], True)
        self.assertEqual(graphic.color.kind, 'show-through')
        self.assertEqual(graphic.color.color, (232, 177, 45, 255))
        self.assertEqual(graphic.opacity, (.55, True))
        self.assertGreater(graphic.depthPriority, 0)

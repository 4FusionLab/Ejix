# SPDX-License-Identifier: GPL-3.0-only
"""Analytical voxel oracle: assert set equality/conservation, not call sequences.

This checks orchestration with multiple solids, cavities and disconnected islands.
It does not simulate Fusion's geometric kernel.
"""
from dataclasses import replace
import copy
import unittest

from Ejix.engine import eject, eject_groups
from Ejix.settings import Settings
from types import SimpleNamespace as NS


def box(x0, x1, y0=0, y1=4, z0=0, z1=4):
    return {(x, y, z) for x in range(x0, x1) for y in range(y0, y1) for z in range(z0, z1)}


class Oracle:
    def __init__(self, originals, tool):
        self.solids = copy.deepcopy(originals)
        self.initial = copy.deepcopy(originals)
        self.tool, self.components = tool, {}
        self.counter = 0
        self.cut_early = False

    def volume(self, body):
        return len(self.solids[body])

    def intersection_volume(self, source, profiles, settings):
        return len(self.solids[source] & self.tool)

    def extract(self, source, profiles, settings):
        if self.solids[source] != self.initial[source]:
            self.cut_early = True
        intersection = self.solids[source] & self.tool
        if not intersection:
            return ()
        result = source + '_ejected'
        self.solids[result] = intersection
        return (result,)

    def subtract(self, source, pieces):
        for piece in pieces:
            self.solids[source] -= self.solids[piece]

    def to_component(self, piece, index):
        self.components[piece] = 'child_' + str(index)
        return piece

    def finish(self, settings):
        return 'Eject' if settings.execution == 'eject' else None

    def abort(self):
        self.solids = copy.deepcopy(self.initial)
        self.components.clear()

    def run(self, settings=Settings(execution='native')):
        try:
            return eject(self, ['profile'], tuple(self.initial), settings)
        except Exception:
            self.abort()
            raise


class EngineTests(unittest.TestCase):
    def test_combined_regions_cut_once_after_extracting_all(self):
        class Backend:
            def __init__(self):
                self.solid = set(range(10))
                self.events = []
            def extract(self, body, profiles, settings):
                self.events.append('extract')
                return [self.solid & profiles[0]]
            def volume(self, piece): return len(piece)
            def merge_connected(self, body, pieces):
                self.events.append('join')
                return [set().union(*pieces)]
            def subtract(self, body, pieces):
                self.events.append('cut')
                self.solid -= set().union(*pieces)
            def finish(self, settings): return None
        backend = Backend()
        hit = NS(body='a', original_volume=10, extracted_volume=6)
        current = NS(body='a', original_volume=10, extracted_volume=4)
        settings = replace(Settings(), execution='native', region_mode='combined')
        result = eject_groups(backend, [[{1, 2, 3, 4}], [{3, 4, 5, 6}]], [hit], [[current], [current]], settings)
        self.assertEqual(result.bodies, ({1, 2, 3, 4, 5, 6},))
        self.assertEqual(backend.solid, {0, 7, 8, 9})
        self.assertEqual(backend.events, ['extract', 'extract', 'join', 'cut'])
    def test_multiple_planes_extract_in_order_and_keep_first_overlap(self):
        class GroupOracle:
            def __init__(self):
                self.original = set(range(10))
                self.events = []
            def extract(self, body, profiles, settings, excluded=()):
                self.events.append(('extract', body))
                return [(set(profiles[0]) & self.original) - set().union(*excluded)]
            def volume(self, piece):
                return len(piece)
            def subtract(self, body, pieces):
                self.events.append(('cut', body))
                self.original -= set().union(*pieces)
            def finish(self, settings):
                return None
        backend = GroupOracle()
        hit = NS(body='a', original_volume=10, extracted_volume=6)
        first = NS(body='a', original_volume=10, extracted_volume=4)
        second = NS(body='a', original_volume=10, extracted_volume=2)
        result = eject_groups(backend, [[{1, 2, 3, 4}], [{3, 4, 5, 6}]], [hit], [[first], [second]], Settings(execution='native'))
        self.assertEqual(result.bodies, ({1, 2, 3, 4}, {5, 6}))
        self.assertEqual(backend.original, {0, 7, 8, 9})
        self.assertEqual(backend.events, [('extract', 'a'), ('extract', 'a'), ('cut', 'a')])

    def test_multiple_planes_reject_changed_result_before_cut(self):
        class ChangedOracle:
            def extract(self, body, profiles, settings, excluded=()): return [{1}]
            def volume(self, piece): return len(piece)
            def subtract(self, *args): raise AssertionError('must not cut')
        hit = NS(body='a', original_volume=10, extracted_volume=4)
        with self.assertRaisesRegex(ValueError, 'changed after preview'):
            eject_groups(ChangedOracle(), [[1], [2]], [hit], [[hit], []], Settings(execution='native'))

    def test_multibody_conservation_in_both_timeline_modes(self):
        originals = {'a': box(0, 4), 'b': box(5, 10), 'c': box(12, 16)}
        tool = box(-2, 20, 1, 3)
        for mode in ('native', 'eject'):
            with self.subTest(mode=mode):
                backend = Oracle(originals, tool)
                result = backend.run(replace(Settings(), execution=mode))
                self.assertEqual(len(result.bodies), 3)
                for source, original in originals.items():
                    part = backend.solids[source + '_ejected']
                    remaining = backend.solids[source]
                    self.assertEqual(part, original & tool)
                    self.assertEqual(remaining, original - tool)
                    self.assertFalse(part & remaining)
                    self.assertEqual(part | remaining, original)

    def test_copy_only_preserves_all_originals(self):
        originals = {'a': box(0, 5), 'b': box(5, 10)}
        backend = Oracle(originals, box(2, 8))
        result = backend.run(replace(Settings(), subtract=False))
        self.assertEqual(len(result.bodies), 2)
        for key, cells in originals.items():
            self.assertEqual(backend.solids[key], cells)

    def test_holes_and_disconnected_regions_survive(self):
        solid = box(0, 10) - box(3, 7, 1, 3)
        tool = box(1, 2) | box(8, 9)
        backend = Oracle({'cavity': solid}, tool)
        backend.run()
        self.assertEqual(backend.solids['cavity_ejected'], solid & tool)

    def test_overlapping_sources_keep_independent_identity(self):
        originals = {'a': box(0, 7), 'b': box(4, 10)}
        tool = box(5, 6)
        backend = Oracle(originals, tool)
        backend.run()
        for source in originals:
            self.assertEqual(backend.solids[source], originals[source] - tool)

    def test_new_component_contains_each_result(self):
        backend = Oracle({'a': box(0, 4), 'b': box(5, 9)}, box(-1, 12, 1, 2))
        result = backend.run(replace(Settings(), execution='native', result='component'))
        self.assertEqual(set(backend.components), set(result.bodies))
        self.assertEqual(len(set(backend.components.values())), 2)

    def test_later_miss_leaves_no_partial_results(self):
        originals = {'hit': box(0, 4), 'miss': box(8, 10)}
        backend = Oracle(originals, box(1, 2))
        with self.assertRaisesRegex(ValueError, 'intersect'):
            backend.run()
        self.assertEqual(backend.solids, originals)

    def test_entire_body_is_ignored_while_partial_body_is_extracted(self):
        originals = {'partial': box(0, 4), 'whole': box(6, 7)}
        backend = Oracle(originals, box(2, 10))
        result = backend.run()
        self.assertEqual(result.bodies, ('partial_ejected',))
        self.assertEqual(backend.solids['whole'], originals['whole'])
        self.assertNotIn('whole_ejected', backend.solids)
        self.assertEqual(backend.solids['partial'], box(0, 2))

    def test_entire_body_copy_is_allowed(self):
        backend = Oracle({'whole': box(0, 4)}, box(-1, 10))
        result = backend.run(replace(Settings(), subtract=False))
        self.assertEqual(backend.solids[result.bodies[0]], backend.initial['whole'])

    def test_all_whole_bodies_create_no_results_or_components(self):
        originals = {'whole': box(0, 4)}
        backend = Oracle(originals, box(-1, 10))
        with self.assertRaisesRegex(ValueError, 'ignored'):
            backend.run(replace(Settings(), result='component'))
        self.assertEqual(backend.solids, originals)
        self.assertFalse(backend.components)

    def test_all_extractions_precede_source_changes(self):
        class WatchingOracle(Oracle):
            def extract(self, source, profiles, settings):
                for key in self.initial:
                    if self.solids[key] != self.initial[key]:
                        raise AssertionError('An original changed before all extractions completed.')
                return super().extract(source, profiles, settings)
        backend = WatchingOracle({'a': box(0, 5), 'b': box(6, 10)}, box(-1, 12, 1, 2))
        backend.run()
        self.assertFalse(backend.cut_early)

    def test_missing_selections_rejected(self):
        for profiles, bodies in (([], ['a']), (['profile'], [])):
            with self.assertRaises(ValueError):
                eject(Oracle({'a': box(0, 4)}, box(1, 2)), profiles, bodies, Settings())

    def test_subtraction_failure_rolls_back_every_source(self):
        class FailingOracle(Oracle):
            def subtract(self, source, pieces):
                super().subtract(source, pieces)
                if source == 'b':
                    raise RuntimeError('kernel failure')
        originals = {'a': box(0, 5), 'b': box(6, 10)}
        backend = FailingOracle(originals, box(-1, 12, 1, 2))
        with self.assertRaisesRegex(RuntimeError, 'kernel failure'):
            backend.run()
        self.assertEqual(backend.solids, originals)

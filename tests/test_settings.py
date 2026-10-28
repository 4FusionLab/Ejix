# SPDX-License-Identifier: GPL-3.0-only
from dataclasses import replace
import json
import math
import unittest

from Ejix.settings import Settings, EXECUTIONS
from Ejix.scope import coplanar


class SettingsTests(unittest.TestCase):
    def test_defaults_and_roundtrip(self):
        settings = Settings()
        self.assertEqual((settings.execution, settings.result, settings.subtract), ('eject', 'body', True))
        self.assertEqual(dict(EXECUTIONS)['eject'], 'Eject Feature')
        for direction in ('one', 'two', 'symmetric'):
            for extent in ('distance', 'all'):
                s = replace(settings, direction=direction, extent=extent, distance='Width / 2')
                self.assertEqual(Settings.decode(s.encode()), s)

    def test_schema_rejected(self):
        for data in ({'schema': 2, 'settings': {}}, {'schema': 1, 'settings': None}):
            with self.assertRaises(ValueError):
                Settings.decode(json.dumps(data))

    def test_options_rejected(self):
        for key in ('execution', 'result', 'direction', 'extent', 'start'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                replace(Settings(), **{key: 'unknown'}).validate()

    def test_nonboolean_options_rejected(self):
        for key in ('subtract', 'flipped'):
            with self.assertRaises(ValueError):
                replace(Settings(), **{key: 'false'}).validate()

    def test_numeric_distance_rules(self):
        for number in (0, -1, math.inf, math.nan):
            with self.subTest(number=number), self.assertRaises(ValueError):
                Settings().validate(lambda expr: 0 if expr == '0 mm' else number)

    def test_hidden_distance_is_not_evaluated_for_all(self):
        calls = []
        replace(Settings(), extent='all', distance='MissingParameter').validate(lambda expr: calls.append(expr) or 0)
        self.assertEqual(calls, [])

    def test_legacy_offset_start_is_preserved(self):
        raw = json.loads(Settings(offset='-2 mm').encode())
        del raw['settings']['start']
        self.assertEqual(Settings.decode(json.dumps(raw)).start, 'offset')

    def test_missing_execution_in_legacy_data_keeps_native_mode(self):
        raw = json.loads(Settings().encode())
        del raw['settings']['execution']
        self.assertEqual(Settings.decode(json.dumps(raw)).execution, 'native')

    def test_existing_feature_without_region_mode_preserves_legacy_grouping(self):
        raw = json.loads(Settings().encode())
        del raw['settings']['region_mode']
        self.assertEqual(Settings.decode(json.dumps(raw)).region_mode, 'legacy')

    def test_new_region_modes_roundtrip(self):
        for mode in ('separate', 'combined'):
            settings = replace(Settings(), region_mode=mode)
            self.assertEqual(Settings.decode(settings.encode()), settings)
        with self.assertRaises(ValueError):
            replace(Settings(), region_mode='invalid').validate()

    def test_second_distance_validated_only_for_two_sides(self):
        s = replace(Settings(), distance='good', distance_two='bad')
        evaluate = lambda expr: {'0 mm': 0, 'good': 1, 'bad': -1}[expr]
        s.validate(evaluate)
        with self.assertRaises(ValueError):
            replace(s, direction='two').validate(evaluate)

    def test_negative_offset_is_valid(self):
        replace(Settings(), offset='-2 mm').validate(lambda expr: -0.2 if expr == '-2 mm' else 1)


class PlaneTests(unittest.TestCase):
    def test_rotated_translated_and_reversed(self):
        self.assertTrue(coplanar([((4, 9, 2), (1, 1, 0)), ((5, 8, 7), (-2, -2, 0))]))

    def test_parallel_offset_is_not_coplanar(self):
        self.assertFalse(coplanar([((0, 0, 0), (0, 0, 1)), ((0, 0, 0.001), (0, 0, 1))]))

    def test_crossing_planes_are_not_coplanar(self):
        self.assertFalse(coplanar([((0, 0, 0), (0, 0, 1)), ((0, 0, 0), (1, 0, 0))]))

    def test_degenerate_normal_rejected(self):
        with self.assertRaises(ValueError):
            coplanar([((0, 0, 0), (0, 0, 0))])

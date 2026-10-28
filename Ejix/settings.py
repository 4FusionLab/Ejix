# SPDX-License-Identifier: GPL-3.0-only
"""Versioned command settings. Length values at the API boundary are cm."""
from dataclasses import asdict, dataclass
import json
import math

SCHEMA = 1
EXECUTIONS = (('native', 'Native Features'), ('eject', 'Eject Feature'))
RESULTS = (('body', 'New Body'), ('component', 'New Component'))
DIRECTIONS = (('one', 'One Side'), ('two', 'Two Sides'), ('symmetric', 'Symmetric'))
EXTENTS = (('distance', 'Distance'), ('object', 'To Object'), ('all', 'All'))
STARTS = (('profile', 'Profile Plane'), ('offset', 'Offset'), ('object', 'Object'))
REGION_MODES = (('separate', 'Separate Bodies'), ('combined', 'Combine Connected'))


@dataclass(frozen=True)
class Settings:
    execution: str = 'eject'
    result: str = 'body'
    region_mode: str = 'separate'
    subtract: bool = True
    direction: str = 'one'
    extent: str = 'distance'
    start: str = 'profile'
    flipped: bool = False
    distance: str = '10 mm'
    distance_two: str = '10 mm'
    offset: str = '0 mm'
    object_offset: str = '0 mm'
    object_offset_two: str = '0 mm'

    def validate(self, evaluate=None):
        for key, options in (('execution', EXECUTIONS), ('result', RESULTS),
                             ('direction', DIRECTIONS), ('extent', EXTENTS), ('start', STARTS)):
            if getattr(self, key) not in dict(options):
                raise ValueError('Unknown ' + key + '.')
        if self.region_mode not in ('separate', 'combined', 'legacy'):
            raise ValueError('Unknown region_mode.')
        if type(self.subtract) is not bool or type(self.flipped) is not bool:
            raise ValueError('Subtract and Flip must be Boolean values.')
        if self.extent == 'object' and self.direction == 'symmetric':
            raise ValueError('To Object requires One Side or Two Sides.')
        for key in ('distance', 'distance_two', 'offset', 'object_offset', 'object_offset_two'):
            expression = getattr(self, key)
            if not isinstance(expression, str) or not expression.strip():
                raise ValueError('Enter a length expression for ' + key + '.')
        if evaluate:
            keys = ['offset'] if self.start != 'profile' else []
            if self.extent == 'distance':
                keys.append('distance')
                if self.direction == 'two':
                    keys.append('distance_two')
            elif self.extent == 'object':
                keys.append('object_offset')
                if self.direction == 'two':
                    keys.append('object_offset_two')
            for key in keys:
                number = evaluate(getattr(self, key))
                if not math.isfinite(number) or (key in ('distance', 'distance_two') and number <= 1e-7):
                    raise ValueError('Distances must be positive. Use Flip for the other direction.')
        return self

    def encode(self):
        self.validate()
        return json.dumps({'schema': SCHEMA, 'settings': asdict(self)}, sort_keys=True)

    @classmethod
    def decode(cls, raw):
        data = json.loads(raw)
        if data.get('schema') != SCHEMA or not isinstance(data.get('settings'), dict):
            raise ValueError('Unsupported Eject Feature data. Keep the original add-in version.')
        settings = dict(data['settings'])
        if 'execution' not in settings:
            settings['execution'] = 'native'
        if 'region_mode' not in settings:
            settings['region_mode'] = 'legacy'
        # Earlier prototypes always used an OffsetStartDefinition.
        if 'start' not in settings:
            settings['start'] = 'offset'
        return cls(**settings).validate()

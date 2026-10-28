# SPDX-License-Identifier: GPL-3.0-only
"""Native Extrude-style controls; graphics-only preview; modeling only on OK."""
from dataclasses import replace
from pathlib import Path
import html
import math
import traceback

import adsk.core
import adsk.fusion

from . import engine, fusion_adapter as adapter, preview, ui_resources
from .settings import Settings, EXECUTIONS, RESULTS, DIRECTIONS, EXTENTS, STARTS, REGION_MODES

COMMAND_ID = '4FusionLab_Ejix_Eject'
EDIT_ID = '4FusionLab_Ejix_Edit'
RESOURCE = str(Path(__file__).parent / 'resources' / 'eject')
RESTORE_EVENT = '4FusionLab_Ejix_RestoreTimeline'
LENGTHS = ('distance', 'distance_two', 'offset', 'object_offset', 'object_offset_two')
_bindings = []
_sessions = []
_control = None
_restores = []
_restore_registered = False


def bind(event, handler, bindings):
    if not event.add(handler):
        raise RuntimeError('Unable to register an Ejix event handler.')
    bindings.append((event, handler))


def log_error():
    adsk.core.Application.get().log('Ejix: ' + traceback.format_exc())


def selected(input_):
    return [input_.selection(i).entity for i in range(input_.selectionCount)]


def length_expression(control, units):
    """Return an expression matching the live value, not a stale drag text.

    Fusion updates DistanceValueCommandInput.value while its manipulator is
    dragged but leaves .expression at the value from before the drag. Reading
    .expression during inputChanged therefore previews an older extent, while
    the command commits the current one. Use the live value whenever the two
    disagree; keep the original expression otherwise so parameters survive.
    """
    expression = control.expression
    if not control.isValidExpression:
        return expression
    if abs(units.evaluateExpression(expression, 'cm') - control.value) <= 1e-9:
        return expression
    if not math.isfinite(control.value):
        return expression
    # Fixed-point text avoids locale decimal separators and grouping. Nine
    # decimals of a centimetre stay far below model precision.
    return (('%.9f' % control.value).rstrip('0').rstrip('.') or '0') + ' cm'


class Session:
    def __init__(self, command, custom=None):
        self.command, self.custom = command, custom
        self.app = adsk.core.Application.get()
        self.document = self.app.activeDocument
        self.design = adsk.fusion.Design.cast(self.app.activeProduct)
        self.bindings, self.inputs = [], {}
        selections = self.app.userInterface.activeSelections
        self.preselected = [selections.item(i).entity for i in range(selections.count)]
        self.analysis, self.renderer = preview.GroupAnalysis(), preview.Renderer()
        self.seeded = self.updating = self.arrow_ready = False
        self.error = ''
        self.frame = None
        self.auto_direction = False
        self.oriented = None
        self.hits, self.object_bodies, self.excluded = (), [], []
        self.object_rows = []
        self.object_pool = []
        self.object_row_id = 0
        self.restore_marker = self.design.timeline.markerPosition
        self.restore_anchor = self.design.timeline.item(self.restore_marker - 1) if self.restore_marker else None
        settings = Settings()
        if custom:
            from . import feature
            settings = feature.read(custom)
        self.initial = settings
        command.isExecutedWhenPreEmpted = False
        command.isRepeatable = False
        command.okButtonText = 'OK'
        command.setDialogInitialSize(370, 560)
        inputs = command.commandInputs
        if not custom:
            control = inputs.addSelectionInput('profiles', 'Profiles', 'Select closed profiles or planar faces')
            control.addSelectionFilter('Profiles')
            control.addSelectionFilter('PlanarFaces')
            control.setSelectionLimits(1, 0)
            self.inputs['profiles'] = control
        self.dropdown(inputs, 'start', 'Start', STARTS, settings.start)
        start_object = inputs.addSelectionInput('start_object', 'Start Object', 'Select a parallel planar face or construction plane')
        start_object.addSelectionFilter('PlanarFaces')
        start_object.addSelectionFilter('ConstructionPlanes')
        start_object.setSelectionLimits(0, 1)
        self.inputs['start_object'] = start_object
        self.inputs['offset'] = inputs.addValueInput('offset', 'Offset', self.design.unitsManager.defaultLengthUnits,
                                                    adapter.value(settings.offset))
        self.dropdown(inputs, 'direction', 'Direction', DIRECTIONS, settings.direction)
        self.inputs['flipped'] = inputs.addBoolValueInput('flipped', 'Flip Direction', False,
                                                        ui_resources.icon('reverse'), settings.flipped)
        self.dropdown(inputs, 'extent', 'Extent Type', EXTENTS, settings.extent)
        for key, label in (('target', 'Object'), ('target_two', 'Object 2')):
            control = inputs.addSelectionInput(key, label, 'Select a planar face or construction plane')
            control.addSelectionFilter('PlanarFaces')
            control.addSelectionFilter('ConstructionPlanes')
            control.setSelectionLimits(0, 1)
            self.inputs[key] = control
        for key, label in (('distance', 'Distance'), ('distance_two', 'Distance 2')):
            control = inputs.addDistanceValueCommandInput(key, label, adapter.value(getattr(settings, key)))
            control.minimumValue = 0
            # Accept zero so Fusion commits the typed expression and notifies
            # inputChanged. Settings validation still rejects a zero distance
            # on OK; an exclusive minimum silently kept the previous value and
            # left its old preview on screen.
            control.isMinimumValueInclusive = True
            control.isEnabled = False
            self.inputs[key] = control
        for key, label in (('object_offset', 'Offset'), ('object_offset_two', 'Offset 2')):
            self.inputs[key] = inputs.addValueInput(key, label, self.design.unitsManager.defaultLengthUnits,
                                                    adapter.value(getattr(settings, key)))
        self.dropdown(inputs, 'execution', 'Timeline', EXECUTIONS, settings.execution)
        self.dropdown(inputs, 'result', 'Operation', RESULTS, settings.result)
        self.dropdown(inputs, 'region_mode', 'Profile Results', REGION_MODES,
                      'separate' if settings.region_mode == 'legacy' else settings.region_mode)
        self.inputs['region_note'] = inputs.addTextBoxCommandInput(
            'region_note', '', 'Separate results are cut in the order the profiles were selected.', 2, True)
        self.inputs['region_note'].isFullWidth = True
        self.inputs['objects'] = inputs.addGroupCommandInput('objects', 'Objects to Eject')
        self.inputs['objects'].isExpanded = True
        self.inputs['objects'].tooltip = 'Intersecting bodies are found automatically. Uncheck a body to exclude it.'
        # Create controls during commandCreated. Fusion does not consistently
        # notify inputChanged for checkboxes first added by executePreview.
        for component in self.design.allComponents:
            for body in component.bRepBodies:
                if body.isSolid:
                    row = self.add_object_row(body, True)
                    row.isVisible = False
                    self.object_pool.append((body, row))
        self.inputs['subtract'] = inputs.addBoolValueInput('subtract', 'Subtract from Objects', True,
                                                         ui_resources.icon('cut'), settings.subtract)
        self.inputs['preview'] = inputs.addBoolValueInput('preview', 'Preview', True, '', True)
        self.inputs['status'] = inputs.addTextBoxCommandInput('status', '', '', 2, True)
        self.inputs['status'].isFullWidth = True
        if custom:
            from . import feature
            self.object_bodies = feature.original_bodies(custom)
            for body in self.object_bodies:
                row = self.object_row(body)
                row.isVisible = True
                self.object_rows.append(row)
            for key in ('execution', 'result', 'region_mode', 'subtract', 'objects'):
                self.inputs[key].isEnabled = False
                self.inputs[key].tooltip = 'Fixed when this Eject Feature was created.'
            for key, entity in zip(('target', 'target_two', 'start_object'), feature.targets(custom)):
                if entity and entity.isValid:
                    self.inputs[key].addSelection(entity)
        self.sync()
        bind(command.activate, Activated(self), self.bindings)
        bind(command.inputChanged, Changed(self), self.bindings)
        bind(command.validateInputs, Validated(self), self.bindings)
        bind(command.executePreview, Previewed(self), self.bindings)
        bind(command.execute, Executed(self), self.bindings)
        bind(command.destroy, Destroyed(self), self.bindings)

    def dropdown(self, inputs, key, label, options, current):
        control = inputs.addDropDownCommandInput(key, label, adsk.core.DropDownStyles.LabeledIconDropDownStyle)
        for value, text in options:
            icon = 'start_object' if key == 'start' and value == 'object' else value
            resource = '' if key == 'execution' and value == 'eject' else ui_resources.icon(icon)
            control.listItems.add(text, value == current, resource)
        self.inputs[key] = control

    def choice(self, key, options):
        return options[self.inputs[key].selectedItem.index][0]

    def settings(self):
        direction = self.choice('direction', DIRECTIONS)
        extent = self.choice('extent', EXTENTS)
        lengths = {key: length_expression(self.inputs[key], self.design.unitsManager) for key in LENGTHS}
        flipped = self.inputs['flipped'].value
        mode = self.choice('region_mode', REGION_MODES) if 'region_mode' in self.inputs else 'separate'
        if getattr(self, 'custom', None) and self.initial.region_mode == 'legacy':
            mode = 'legacy'
        distance = self.inputs['distance']
        if direction == 'one' and extent == 'distance' and distance.isValidExpression and distance.value < 0:
            lengths['distance'] = '-(' + lengths['distance'] + ')'
            flipped = not flipped
        return Settings(execution=self.choice('execution', EXECUTIONS), result=self.choice('result', RESULTS),
                        start=self.choice('start', STARTS),
                        subtract=self.inputs['subtract'].value, direction=direction,
                        extent=extent, flipped=flipped, region_mode=mode, **lengths)

    def targets(self):
        return tuple(self.inputs[key].selection(0).entity if self.inputs[key].selectionCount else None
                     for key in ('target', 'target_two', 'start_object'))

    def orient_inward(self):
        """Aim One Side into the material of the face a sketch is built on."""
        if self.custom:
            return
        sources = self.profiles()
        if not sources:
            self.oriented = None
            return
        source = adapter.native(sources[0])
        if source == self.oriented:
            return
        self.oriented = source
        outward = adapter.support_normal(sources[0])
        if outward is None:
            return
        _, normal = adapter.plane(sources[0])
        normal.normalize()
        # The analysis extrudes along the sketch +Z. A positive dot means that
        # direction leaves the material, so Flip must point it inward.
        flipped = normal.dotProduct(outward) > 0
        if self.inputs['flipped'].value == flipped:
            return
        had_update, self.updating = self.updating, True
        try:
            self.inputs['flipped'].value = flipped
        finally:
            self.updating = had_update

    def profiles(self):
        if self.custom:
            from . import feature
            return feature.sources(self.custom)
        return adapter.unique(selected(self.inputs['profiles']))

    def status(self, message):
        text = html.escape(message).replace('\n', '<br>')
        if self.inputs['status'].formattedText != text:
            self.inputs['status'].formattedText = text

    def remember_exclusions(self):
        if self.custom:
            return
        for index, body in enumerate(self.object_bodies):
            excluded = not self.object_rows[index].value
            known = any(body == previous for previous in self.excluded)
            if excluded and not known:
                self.excluded.append(body)
            elif not excluded and known:
                self.excluded = [previous for previous in self.excluded if previous != body]

    def add_object_row(self, body, enabled):
        self.object_row_id += 1
        row = self.inputs['objects'].children.addBoolValueInput(
            'ejix_body_' + str(self.object_row_id), body.name, True, '', enabled)
        row.tooltip = 'Include this body in Eject.'
        row.isEnabled = not bool(self.custom)
        return row

    def object_row(self, body):
        native = adapter.native(body)
        for candidate, row in self.object_pool:
            if candidate == native:
                return row
        raise ValueError('Model bodies changed while Eject was open. Restart the command.')

    def update_objects(self):
        if self.custom:
            return
        bodies = [hit.body for hit in self.hits]
        if len(bodies) == len(self.object_bodies) and all(a == b for a, b in zip(bodies, self.object_bodies)):
            return
        self.updating = True
        try:
            for _, row in self.object_pool:
                row.isVisible = False
            self.object_rows.clear()
            self.object_bodies = bodies
            self.excluded = [body for body in self.excluded if body.isValid]
            for body in bodies:
                enabled = not any(body == old for old in self.excluded)
                row = self.object_row(body)
                row.value = enabled
                row.isVisible = True
                self.object_rows.append(row)
        finally:
            self.updating = False

    def active_hits(self):
        if self.custom:
            originals = [adapter.native(body) for body in self.object_bodies]
            hits = tuple(hit for hit in self.hits if any(adapter.native(hit.body) == body for body in originals))
        else:
            hits = tuple(hit for i, hit in enumerate(self.hits) if self.object_rows[i].value)
        return tuple(hit for hit in hits if not self.settings().subtract or
                     not engine.fully_enclosed(hit.original_volume, hit.extracted_volume))

    def sync(self, position=True):
        settings = self.settings()
        profiles = self.profiles()
        distance, to_object = settings.extent == 'distance', settings.extent == 'object'
        two = settings.direction == 'two'
        control = self.inputs['distance']
        if settings.direction == 'one':
            control.hasMinimumValue = False
        elif not control.hasMinimumValue:
            if control.isValidExpression and control.value < 0:
                control.expression = '-(' + length_expression(control, self.design.unitsManager) + ')'
            control.minimumValue = 0
            control.isMinimumValueInclusive = True
        for key, visible in {'flipped': settings.direction == 'one', 'distance': distance,
                             'start_object': settings.start == 'object', 'offset': settings.start != 'profile',
                             'distance_two': distance and two, 'target': to_object,
                             'target_two': to_object and two, 'object_offset': to_object,
                             'object_offset_two': to_object and two}.items():
            self.inputs[key].isVisible = visible
        self.inputs['region_mode'].isVisible = len(profiles) > 1
        self.inputs['region_note'].isVisible = len(profiles) > 1 and settings.region_mode != 'combined'
        if not position:
            return
        self.arrow_ready = False
        if profiles and profiles[0].isValid:
            origin, normal = adapter.plane(profiles[0])
            entity = adapter.native(profiles[0])
            if isinstance(entity, adsk.fusion.Profile):
                origin = entity.parentSketch.sketchToModelSpace(entity.areaProperties().centroid)
            else:
                origin = entity.pointOnFace.copy()
            origin, normal = origin.copy(), normal.copy()
            context = getattr(profiles[0], 'assemblyContext', None)
            if context:
                origin.transformBy(context.transform2); normal.transformBy(context.transform2)
            normal.normalize()
            shift = normal.copy()
            if self.inputs['offset'].isValidExpression:
                shift.scaleBy(adapter.start_offset(self.design, profiles, settings, self.targets())); origin.translateBy(shift)
            if settings.direction == 'one' and self.inputs['flipped'].value:
                normal.scaleBy(-1)
            opposite = normal.copy(); opposite.scaleBy(-1)
            self.arrow_ready = bool(self.inputs['distance'].setManipulator(origin, normal)
                                    and self.inputs['distance_two'].setManipulator(origin, opposite))
        for key in ('distance', 'distance_two'):
            self.inputs[key].isEnabled = self.arrow_ready

    def refresh(self, draw=True):
        self.renderer.clear()
        self.error = ''
        try:
            profiles = self.profiles()
            if not profiles:
                self.hits = ()
                self.update_objects()
                self.status('Select Profiles.')
                return
            settings = self.settings()
            objects = None
            if self.custom:
                from . import feature
                objects = feature.preview_objects(self.custom)
            self.hits = self.analysis.analyze(self.design, profiles, settings, self.targets(), objects)
            if self.auto_direction and not self.hits and settings.extent == 'distance' and settings.direction == 'one':
                self.auto_direction = False
                alternative = replace(settings, flipped=not settings.flipped)
                hits = self.analysis.analyze(self.design, profiles, alternative, self.targets())
                if hits:
                    self.updating = True
                    self.inputs['flipped'].value = alternative.flipped
                    self.updating = False
                    settings, self.hits = alternative, hits
                    self.sync()
            self.auto_direction = False
            self.update_objects()
            active = self.active_hits()
            skipped = sum(engine.fully_enclosed(hit.original_volume, hit.extracted_volume)
                          for hit in self.hits) if settings.subtract else 0
            message = '%d Objects' % len(active) if active else 'No participating Objects. Change the extent or enable an Object.'
            if skipped:
                message += '\n%d fully enclosed Objects ignored.' % skipped
            self.status(message)
            # Updating command inputs can synchronously abort the current
            # preview step. Never put ASM-backed graphics into that step first.
            if draw and self.inputs['preview'].value:
                groups = getattr(self.analysis, 'group_hits', None)
                graphics = (tuple(hit for group in groups for hit in group
                                  if any(hit.body == selected.body for selected in active))
                            if groups and settings.region_mode != 'combined' else active)
                self.renderer.show(self.design, graphics, profiles, settings.subtract)
        except Exception as error:
            self.error = str(error)
            self.hits = ()
            self.update_objects()
            self.status(str(error))
            if not isinstance(error, ValueError):
                log_error()

    def check(self):
        if self.app.activeDocument != self.document or not self.design.isValid:
            raise ValueError('Return to the design where Eject was started.')
        if self.error:
            raise ValueError(self.error)
        profiles, settings = self.profiles(), self.settings()
        hits = self.active_hits()
        bodies = [hit.body for hit in hits]
        component = adapter.validate(self.design, profiles, bodies, settings, self.targets(),
                                     allow_multiple_planes=True)
        return settings, component, profiles, bodies


class Activated(adsk.core.CommandEventHandler):
    def __init__(self, session):
        super().__init__(); self.session = session

    def notify(self, args):
        session = self.session
        if session.seeded:
            return
        session.seeded = True
        session.updating = True
        try:
            if not session.custom:
                for entity in session.preselected:
                    if entity.isValid and (isinstance(entity, adsk.fusion.Profile) or
                            isinstance(entity, adsk.fusion.BRepFace) and isinstance(entity.geometry, adsk.core.Plane)):
                        session.inputs['profiles'].addSelection(entity)
                session.auto_direction = bool(session.profiles() and isinstance(session.profiles()[0], adsk.fusion.BRepFace))
                session.orient_inward()
            session.sync()
        finally:
            session.updating = False
        session.command.beginStep()
        session.refresh(draw=False)


class Changed(adsk.core.InputChangedEventHandler):
    def __init__(self, session):
        super().__init__(); self.session = session

    def notify(self, args):
        session = self.session
        if session.updating:
            return
        try:
            key = args.input.id
            if key == 'status':
                return
            if key.startswith('ejix_body_'):
                session.remember_exclusions()
            if key == 'profiles':
                session.analysis.reset()
                sources = session.profiles()
                session.auto_direction = bool(sources and isinstance(sources[0], adsk.fusion.BRepFace))
                session.orient_inward()
            if key in ('extent', 'direction') and session.settings().direction == 'symmetric' and session.settings().extent == 'object':
                session.updating = True
                session.inputs['extent'].listItems.item(0).isSelected = True
                session.updating = False
            session.sync(position=not key.startswith('ejix_body_') and key not in
                         ('distance', 'distance_two', 'objects', 'preview', 'subtract', 'result', 'execution'))
            session.refresh(draw=False)
        except Exception as error:
            session.updating = False
            session.renderer.clear()
            session.error = str(error)
            session.status(str(error))
            if not isinstance(error, ValueError):
                log_error()


class Validated(adsk.core.ValidateInputsEventHandler):
    def __init__(self, session):
        super().__init__(); self.session = session

    def notify(self, args):
        try:
            self.session.check()
            args.areInputsValid = True
        except Exception as error:
            args.areInputsValid = False
            self.session.status(str(error))


class Previewed(adsk.core.CommandEventHandler):
    def __init__(self, session):
        super().__init__(); self.session = session

    def notify(self, args):
        # Deliberately never mark graphics as a committable modeling result.
        args.isValidResult = False
        self.session.refresh()


class Executed(adsk.core.CommandEventHandler):
    def __init__(self, session):
        super().__init__(); self.session = session

    def notify(self, args):
        session = self.session
        session.renderer.clear()
        session.refresh(draw=False)
        try:
            settings, component, profiles, bodies = session.check()
            if session.custom:
                from . import feature
                feature.update(session.custom, settings, session.targets())
            else:
                groups = preview.profile_groups(profiles, settings.region_mode != 'legacy') if len(profiles) > 1 else [profiles]
                backend = adapter.Backend(component, session.targets())
                if len(groups) == 1:
                    engine.eject(backend, profiles, bodies, settings)
                else:
                    selected_hits = session.active_hits()
                    engine.eject_groups(backend, groups, selected_hits, session.analysis.group_hits, settings)
        except Exception as error:
            args.executeFailed = True
            args.executeFailedMessage = str(error)
            session.status(str(error))
            if not isinstance(error, ValueError):
                log_error()


class Destroyed(adsk.core.CommandEventHandler):
    def __init__(self, session):
        super().__init__(); self.session = session

    def notify(self, args):
        session = self.session
        session.renderer.clear()
        if session in _sessions:
            _sessions.remove(session)
        if session.custom:
            _restores.append((session.design, session.restore_anchor, session.restore_marker))
        session.bindings.clear()
        session.preselected.clear()
        session.analysis.reset()
        session.excluded.clear()


class Created(adsk.core.CommandCreatedEventHandler):
    def __init__(self, edit=False):
        super().__init__(); self.edit = edit

    def notify(self, args):
        app = adsk.core.Application.get()
        try:
            if not adsk.fusion.Design.cast(app.activeProduct):
                raise ValueError('Open a Fusion design before starting Eject.')
            custom = None
            if self.edit:
                from .feature import DEFINITION_ID
                for i in range(app.userInterface.activeSelections.count):
                    item = adsk.fusion.CustomFeature.cast(app.userInterface.activeSelections.item(i).entity)
                    if item and item.definition and item.definition.id == DEFINITION_ID:
                        custom = item
                        break
                if custom is None:
                    raise ValueError('Select an Eject Feature in the timeline.')
            _sessions.append(Session(args.command, custom))
        except Exception as error:
            log_error()
            app.userInterface.messageBox(str(error), 'Ejix')


class RestoreTimeline(adsk.core.CustomEventHandler):
    def notify(self, args):
        pending = list(_restores)
        _restores.clear()
        for design, anchor, marker in pending:
            try:
                if design.isValid:
                    if anchor and anchor.isValid:
                        anchor.rollTo(False)
                    else:
                        design.timeline.markerPosition = min(marker, design.timeline.count)
            except Exception:
                log_error()


class Terminated(adsk.core.ApplicationCommandEventHandler):
    def notify(self, args):
        if args.commandId == EDIT_ID and _restores:
            # Destroy precedes Fusion's rollback on Cancel. Restore only after
            # the command transaction ends, as established in Perfora.
            adsk.core.Application.get().fireCustomEvent(RESTORE_EVENT)


def run(context):
    global _control, _restore_registered
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        restore_event = app.registerCustomEvent(RESTORE_EVENT)
        _restore_registered = True
        bind(restore_event, RestoreTimeline(), _bindings)
        bind(ui.commandTerminated, Terminated(), _bindings)
        for identifier, name, description, edit in (
                (COMMAND_ID, 'Eject', 'Extract a selected volume into a new body or component.', False),
                (EDIT_ID, 'Edit Eject', 'Edit the extent of an Eject Feature.', True)):
            definition = ui.commandDefinitions.itemById(identifier)
            if definition:
                definition.deleteMe()
            definition = ui.commandDefinitions.addButtonDefinition(identifier, name, description, RESOURCE)
            bind(definition.commandCreated, Created(edit), _bindings)
        panel = ui.allToolbarPanels.itemById('SolidModifyPanel')
        if panel:
            _control = panel.controls.addCommand(ui.commandDefinitions.itemById(COMMAND_ID))
            _control.isPromoted = True
        # Definitions are restored at add-in load, before a saved document asks
        # Fusion to compute its custom nodes. Native mode remains available if
        # a Fusion version lacks the experimental API.
        try:
            from . import feature
            feature.register()
        except Exception:
            log_error()
    except Exception:
        log_error()
        stop(context)
        ui.messageBox('Unable to start Ejix. See the Fusion log.', 'Ejix')


def stop(context):
    global _control, _restore_registered
    app = adsk.core.Application.get()
    if _sessions:
        app.userInterface.terminateActiveCommand()
    if _control and _control.isValid:
        _control.deleteMe()
    _control = None
    for event, handler in reversed(_bindings):
        event.remove(handler)
    _bindings.clear()
    if _restore_registered:
        app.unregisterCustomEvent(RESTORE_EVENT)
        _restore_registered = False
    _restores.clear()
    for identifier in (COMMAND_ID, EDIT_ID):
        definition = app.userInterface.commandDefinitions.itemById(identifier)
        if definition:
            definition.deleteMe()
    try:
        from . import feature
        feature.unregister()
    except (ImportError, AttributeError):
        pass

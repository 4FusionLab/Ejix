# SPDX-License-Identifier: GPL-3.0-only
"""API-independent operation coordinator; the backend owns geometry/transactions."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Result:
    bodies: tuple
    feature: object = None


def fully_enclosed(original_volume, extracted_volume):
    return original_volume - extracted_volume <= max(1e-10, original_volume * 1e-8)


def eject(backend, profiles, bodies, settings):
    """Extract all targets before changing any original; tools survive subtraction.

    Must run inside a backend transaction (Fusion's execute/executePreview).
    An error aborts the complete command, including earlier targets.
    """
    settings.validate()
    if not profiles:
        raise ValueError('Select Profiles or planar faces.')
    if not bodies:
        raise ValueError('Select Objects to eject from.')
    if settings.subtract:
        # Classify before creating copies/features: ignored whole bodies must
        # leave no result, component, or timeline operation behind.
        bodies = tuple(body for body in bodies if not fully_enclosed(
            backend.volume(body), backend.intersection_volume(body, profiles, settings)))
        if not bodies:
            raise ValueError('Fully enclosed Objects are ignored. No partially intersected Objects remain.')
    extracted = []
    for source in bodies:
        original_volume = backend.volume(source)
        pieces = tuple(backend.extract(source, profiles, settings))
        volumes = [backend.volume(piece) for piece in pieces]
        if (not pieces or not math.isfinite(original_volume) or original_volume <= 0
                or any(not math.isfinite(v) or v <= 0 for v in volumes)):
            raise ValueError('Profiles do not intersect every selected Object with a solid volume.')
        volume = sum(volumes)
        tolerance = max(1e-10, original_volume * 1e-8)
        if volume > original_volume + tolerance:
            raise ValueError('The extracted volume exceeds the source Object.')
        if settings.subtract and fully_enclosed(original_volume, volume):
            raise ValueError('The result changed after preview. Restart Eject to update participating Objects.')
        extracted.append((source, pieces))
    # Pair each original with its own pieces. Overlapping sources must never cut
    # one another, even when their extracted volumes occupy the same space.
    if settings.subtract:
        for source, pieces in extracted:
            backend.subtract(source, pieces)
    output = tuple(piece for _, pieces in extracted for piece in pieces)
    if settings.execution == 'eject' and settings.result == 'component':
        feature = backend.finish(settings)
        output = tuple(backend.to_component(piece, index + 1) for index, piece in enumerate(output))
        backend.update_moved_results(feature)
        return Result(output, feature)
    if settings.result == 'component':
        output = tuple(backend.to_component(piece, index + 1) for index, piece in enumerate(output))
    return Result(output, backend.finish(settings))


def eject_groups(backend, groups, hits, group_hits, settings):
    """Extract in selection order, then cut each source with its ordered results."""
    settings.validate()
    if settings.execution == 'eject':
        backend.multi_groups = True
        backend.profiles = tuple(profile for group in groups for profile in group)
    if settings.region_mode == 'combined':
        return eject_combined(backend, groups, hits, group_hits, settings)
    eligible = [hit for hit in hits if not settings.subtract or
                not fully_enclosed(hit.original_volume, hit.extracted_volume)]
    extracted = [(hit.body, []) for hit in eligible]
    for plane_index, (profiles, current_hits) in enumerate(zip(groups, group_hits)):
        for current in current_hits:
            target = next((item for item in extracted if item[0] == current.body), None)
            if target is None:
                continue
            excluded = tuple(target[1]) if settings.subtract else ()
            pieces = tuple(backend.extract(current.body, profiles, settings, excluded=excluded))
            if settings.execution == 'eject':
                backend.step_planes.append(plane_index)
            volume = sum(backend.volume(piece) for piece in pieces)
            if (not pieces or not math.isfinite(volume) or volume <= 0 or
                    abs(volume - current.extracted_volume) > max(1e-8, current.original_volume * 1e-7)):
                raise ValueError('The result changed after preview. Restart Eject to update participating Objects.')
            target[1].extend(pieces)
    output = tuple(piece for _, pieces in extracted for piece in pieces)
    if not output:
        raise ValueError('No partially intersected Objects remain.')
    if settings.subtract:
        for source, pieces in extracted:
            if pieces:
                backend.subtract(source, pieces)
    if settings.execution == 'eject' and settings.result == 'component':
        feature = backend.finish(settings)
        output = tuple(backend.to_component(piece, index + 1) for index, piece in enumerate(output))
        backend.update_moved_results(feature)
        return Result(output, feature)
    if settings.result == 'component':
        output = tuple(backend.to_component(piece, index + 1) for index, piece in enumerate(output))
    return Result(output, backend.finish(settings))


def eject_combined(backend, groups, hits, group_hits, settings):
    """Extract from untouched sources, join connected results, then cut once."""
    eligible = [hit for hit in hits if not settings.subtract or
                not fully_enclosed(hit.original_volume, hit.extracted_volume)]
    extracted = []
    for hit in eligible:
        pieces = []
        for plane_index, (profiles, current_hits) in enumerate(zip(groups, group_hits)):
            current = next((item for item in current_hits if item.body == hit.body), None)
            if current is None:
                continue
            new = tuple(backend.extract(hit.body, profiles, settings))
            if settings.execution == 'eject':
                backend.step_planes.append(plane_index)
            volume = sum(backend.volume(piece) for piece in new)
            if not new or abs(volume - current.extracted_volume) > max(1e-8, hit.original_volume * 1e-7):
                raise ValueError('The result changed after preview. Restart Eject to update participating Objects.')
            pieces.extend(new)
        merged = tuple(backend.merge_connected(hit.body, pieces))
        volume = sum(backend.volume(piece) for piece in merged)
        if not merged or abs(volume - hit.extracted_volume) > max(1e-8, hit.original_volume * 1e-7):
            raise ValueError('The combined result differs from preview. Adjust the selected profiles.')
        extracted.append((hit.body, merged))
    if not extracted:
        raise ValueError('No partially intersected Objects remain.')
    if settings.subtract:
        for body, pieces in extracted:
            backend.subtract(body, pieces)
    output = tuple(piece for _, pieces in extracted for piece in pieces)
    if settings.execution == 'eject' and settings.result == 'component':
        feature = backend.finish(settings)
        output = tuple(backend.to_component(piece, index + 1) for index, piece in enumerate(output))
        backend.update_moved_results(feature)
        return Result(output, feature)
    if settings.result == 'component':
        output = tuple(backend.to_component(piece, index + 1) for index, piece in enumerate(output))
    return Result(output, backend.finish(settings))

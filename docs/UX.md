# UX contract

**English** · [Русский](UX.ru.md) · [Home](../README.md)

## Native interaction

Use Extrude / Cut / Intersect as the reference: native command inputs, native menu icons, distance arrows and expression fields, To Object selection, and an automatic participation list. Ejix separates a volume without moving it in space.

Direction, Extent Type and Operation use LabeledIconDropDownStyle and graphics resolved from the current Fusion installation. Flip uses Fusion's direction icon. Autodesk resources are not copied into the distribution; text is a fallback when the installation lacks a resource.

## Fields

| Field | Behavior |
| --- | --- |
| Profiles | Closed profiles or planar faces, including on different planes |
| Direction | One Side / Two Sides / Symmetric, with native icons |
| Flip Direction | Native icon toggle for One Side |
| Extent Type | Distance / To Object / All, with native icons |
| Object / Object 2 | To Object planar face or construction plane for each side |
| Distance / Distance 2 | Native distance arrows and expressions |
| Offset / Offset 2 | Signed target offsets for To Object |
| Start: Profile Plane / Offset / Object | Signed offset from the Profiles plane |
| Timeline | Eject Feature (default) / Native Features |
| Operation | New Body / New Component, native operation icons |
| Profile Results | Separate Bodies / Combine Connected, shown for multiple profiles |
| Objects to Eject | Automatically detected bodies, checkboxes to disable participation |
| Subtract from Objects | On by default |
| Preview | On by default |

Symmetric uses Half Length and Distance / All. To Object supports One Side and Two Sides. Selecting Symmetric while To Object is active changes Extent Type back to Distance.

When a Profile belongs to a sketch built on a solid face, One Side starts inward, into the material of that face, regardless of the sketch Z direction. Flip reverses it. A profile on a construction plane keeps the plane direction.

## Object discovery

Compute temporary intersections with visible solid bodies in the source component occurrence. Only positive solid intersections appear. All are initially enabled. Preserve exclusions by body identity when dragging or changing extent, including when a body temporarily leaves and re-enters the region. Bodies outside the participation list or unchecked in it remain unchanged.

## Preview is graphics only

The preview path must not create sketches, model BRep bodies, components, Copy/Extrude/Combine features, or move the timeline marker. It must not hide originals or change their appearance. Use exact temporary BRep data and a nonselectable Custom Graphics overlay: translucent golden for subtraction, blue when preserving originals, visible through the original bodies.

Dragging updates temporary intersections and the automatic list. Do not reset the native manipulator while its distance is being dragged. During a drag the live `DistanceValueCommandInput.value` is authoritative because Fusion leaves `.expression` stale; matching expressions are kept so parameters survive. Zero is accepted by the field only so the change is delivered: it clears the preview and validation blocks OK until the distance is positive. `executePreview` always leaves `isValidResult=False`: graphics are not a modeling result that Fusion may commit in place of execute.

OK clears graphics, resolves the enabled bodies and targets again, and runs native modeling once. Cancel / Esc only clears graphics. Native modeling failures abort the final command transaction through executeFailed. Edit Eject also draws graphics until confirmation; timeline changes belong only to final edit execution.

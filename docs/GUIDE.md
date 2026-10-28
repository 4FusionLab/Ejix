# User guide

**English** · [Русский](GUIDE.ru.md) · [Home](../README.md)

## Eject a volume

Eject separates an intersecting volume into a new body without moving it in space. The current implementation uses native Copy, Extrude Intersect and Combine Cut features.

1. Open a parametric design and start **Eject** in the Solid Modify panel or command search.
2. Select one or more closed sketch **Profiles** or planar faces, including on different planes.
3. Intersecting source bodies appear automatically in **Objects to Eject**. Uncheck any body to exclude it. The list updates as the extent changes, and exclusions are retained.
4. Set direction and extent. Drag a distance arrow or enter an expression such as `Width / 2`.
5. Choose the timeline and result settings. Review **Preview** and click **OK**. **Cancel / Esc** cancels the command.

## Direction and extent

| Setting | Meaning |
| --- | --- |
| One Side | Extrude in one direction; drag the arrow across zero or use Flip to reverse it |
| Two Sides | Independent positive and negative distances, with two arrows |
| Symmetric | Equal distances on each side; Distance is Half Length |
| Distance | A length or length expression; a negative value reverses One Side |
| To Object | Up to a planar face or construction plane; independent targets and offsets for Two Sides |
| All | Through all in the selected direction(s); distance arrows are hidden |
| Start: Profile Plane | Begin on the selected profile plane (default) |
| Start: Offset | Begin at a signed offset along the profile normal |
| Start: Object | Begin at a parallel planar face or construction plane, with a signed offset along that object’s normal |

Each plane uses its own local direction and the shared distance and Flip settings. Source objects must share the component and occurrence. With Subtract enabled, planes are processed in selection order: overlap stays with the first plane and later planes use the remaining body. Without Subtract, each profile extracts its full intersection with the original. Both timeline modes support multiple planes.

## One region, multiple bodies

Eject detects every visible intersecting solid in the source component occurrence and lists it with a participation checkbox. After OK, Eject extracts each enabled body's intersection before subtracting from any original. Different sources are not joined, and overlapping sources retain independent results. Bodies without a positive solid intersection are omitted from the automatic list.

## Result options

| Setting | Default | Effect |
| --- | --- | --- |
| Timeline | Eject Feature | Named Eject feature or editable native Copy / Intersect / Cut operations |
| Operation | New Body | Keep results in the source component |
| Subtract from Objects | On | Remove each extracted volume from its original |
| Preview | On | Draw transient intersection volumes without creating bodies or timeline nodes |

With multiple profiles, **Profile Results** offers:

- **Separate Bodies** creates a result for each profile. With subtraction enabled, profiles are processed in selection order, so overlap belongs to the first result.
- **Combine Connected** joins intersecting and touching volumes from each source body before a single subtraction. Disconnected volumes remain separate, and results from different source bodies are not joined.

For Eject Feature, this choice is fixed at creation; recreate the feature to change it.

**New Component** creates a child component for each resulting body. If Intersect returns several bodies, all are retained. Turning subtraction off keeps each original and its intersecting copy.

**Eject Feature** groups the same native graph under a named Eject node. **Edit Eject** updates direction, extent and offset in place. Source selections, Operation and Subtract are fixed at creation. Recreate Eject to change them. Native operations own the parameters; there is no duplicated custom parameter set.

If an edit changes which planes intersect which bodies, Eject Feature may need to be recreated. For New Component, result moves appear after the Eject node in the timeline; changing whole-body participation also requires recreation.

## Preview and history

Preview computes temporary BRep intersections and displays a golden translucent extraction volume (blue when originals are preserved). It creates no design bodies, components or features. OK clears the graphics and creates the result; Cancel removes the overlay. Edit uses the same preview, with timeline changes applied on confirmation.

## Limitations

- Capture Design History is required. Direct Modeling is unsupported.
- Sources must be closed profiles or planar faces. Start Object requires a parallel plane for each profile; a start face must contain the full projected profile, as required by Fusion.
- All sources and Objects must share one component and assembly context.
- Automatic discovery is limited to visible solid bodies in the source component occurrence.
- Fully enclosed bodies are ignored when Subtract is enabled; partially intersected bodies continue. Ignored bodies are not previewed or copied. Disable Subtract to allow whole-body copies.
- To Object supports planar faces and construction planes, not curved targets or Symmetric extent. Taper Angle and splitting disconnected lumps inside one BRepBody are not implemented.
- Eject Feature uses the Fusion Custom Feature API, which Autodesk designates as Preview.

For installation errors and diagnostics, see [Support](../SUPPORT.md).

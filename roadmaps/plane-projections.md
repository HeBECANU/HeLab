# Plane projections (Basic plots v2)

Tony, 2026-11-10 (terminal): "draw a 2D plane in the 3D scatter and show all hits flattened to that 2D plane …
multiple planes, then XY XT YT will just be the special case of plane flattening".

## Decided (Tony, 2026-11-10)

1. **Velocity space (a).** Planes live in (v_x, v_y, v_z) at release, so that a plane may lean towards the vertical
   axis: T (s) and X, Y (m) share no unit, velocities do. t_r and the origin follow the Velocity distributions
   plot's rule (`release.run_velocity_source`: layers, else detected).
2. **Rotation allowed for this plot.** AGENTS.md's "never rotate XY" has this plot as its one exception: a custom
   plane may have any orientation, and ψ turns its axes in the plane.
3. **Four fixed slots**, each on/off with a preset (XY, XT, YT) or custom, three angles (across direction α, tilt θ,
   in-plane rotation ψ), a centre and a thickness (0 = every event, the normal axis summed). Defaults: XY, XT and
   YT on, the fourth custom (α 45°, θ 45°) off.
4. **Planes set by numbers**, drawn in the 3D view and redrawn as the settings change; no mouse drawing.
5. **One new plot**, "Plane projections" (`helab.v2.plane_projections`): the 3D view above, one histogram per plane
   below, one set of settings. "XY, XT, YT histograms" stays as it is.

## Built (2026-11-10, `dev/v0.0.9`)

- `helab/analysis/planes.py` (pure): `Plane` (basis from the angles; the presets' vectors exact), `project`,
  `plane_image` (shortest-range or fixed half-width axes, Freedman–Diaconis or set bins), `PlaneImage.corners`.
- `helab/scripts/standard_v2/plane_projections.py`: the plot; Plotly (default: 3D `Mesh3d` planes over a row of
  heatmaps at equal scales, the camera kept by `uirevision`) and Matplotlib (for a PC without web views). Colour
  compression (sqrt, log, power γ) as the 2D histograms. Results cache through `cache_types`.
- `tests/test_basic_plots_v2_plane_projections.py`: presets = custom at their angles, orthonormal bases, slices,
  a tilted ring, a halo slice's radius, the codec, both libraries in place.

## Later (offer to Tony, not started)

- PyQtGraph drawing (GL 3D view beside `ImageItem` panels) with colour bars, as the other v2 plots.
- Colour bars: each panel is coloured over its own peak (hover gives counts); a shared or per-panel bar.
- Drag handles for a plane in the 3D view (PyQtGraph GL only).
- Live reruns keep the t_r detection (`KeptRuns`, as Velocity distributions) — today each run detects again.
- Recoil-unit centre and thickness (they are set in mm/s whatever the display unit).
- A slot count beyond four, or a list parameter kind.

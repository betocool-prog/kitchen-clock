# 6. CAD tooling and enclosure workflow

Date: 2026-08-23

## Status

Accepted.

## Context

Mechanical enclosures (main-unit frame, sensor-unit enclosures) need a
CAD workflow. Project-level constraints:

- The firmware and electrical design must stay open-source
  (firmware sources in this repo, hardware notes and BOM in this
  repo). Mechanical design is the user's own work, not a deliverable.
- No custom printed circuit boards will be designed or fabricated in
  this project. All wiring is point-to-point, hand-soldered.
- The user is experienced with Onshape (free tier, cloud CAD,
  designs viewable publicly by default) — a non-FOSS source format
  but acceptable for the mechanical deliverables since the user
  owns the geometry and licensing decision.

Earlier documents mentioned KiCad (for any custom PCB carriers) and
OpenSCAD (for in-repo mechanical sources) as fallback choices. Both
are no longer in play.

## Decision

**Onshape** is the user's chosen CAD tool for both the main-unit
frame and the sensor-unit enclosures. The Onshape document URLs will
be added to the relevant `hardware/` READMEs once the user has the
documents live. The Onshape source files themselves stay in Onshape's
cloud rather than this repo.

No **KiCad** PCBs. No **OpenSCAD** mechanical sources in this repo.
The `hardware/main-unit/openscad/` placeholder directory created
during the original spec phase is removed.

## Consequences

- The source-of-truth for the enclosure geometry is in Onshape's
  cloud; this repo holds the BOM and assembly notes, not the CAD
  files. Anyone replicating the build will need a free Onshape
  account.
- Mechanical sources are publicly viewable in Onshape by default
  under their free-tier terms; this is acceptable for this project's
  "open as much as possible" mandate because the user is the
  designer, not a contractor on behalf of the project.
- Point-to-point wiring replaces any future KiCad carrier PCB. The
  harness routes are documented in `hardware/main-unit/README.md`
  and `hardware/sensor-unit/README.md`.
- The `LICENSES/README.md` no longer lists CERN-OHL variants; the
  mechanical licence narrative is now null (the user owns the design
  under Onshape's free-tier terms).

# Licences

Project licensing is **TBD before the first source commit**.

## Likely shape

- **Project source** (firmware, scripts, configs, this ADR set):
  **Apache-2.0** or **MIT**, with file-level SPDX headers.
- **Documentation, ADRs, BOM, README**: **CC BY 4.0**.

## Mechanical sources

Enclosure geometry lives in the user's **Onshape** account under the
free tier (public-by-default viewable documents). See ADR 0006.

- The Onshape free tier allows public viewing of geometry but does
  not impose a particular open-source licence on derivatives.
- The user owns the geometry and chooses whether to publish any
  further licence on the Onshape documents.
- For projects that demand a fully open source mechanical source,
  exporting STL / STEP from Onshape and re-publishing under a
  CERN-OHL-W or CC BY-SA licence is straightforward and the user
  can do it on request.

There are **no KiCad PCB sources** in this project (point-to-point
wiring only; see ADR 0006), and **no OpenSCAD mechanical sources**
in this repo.

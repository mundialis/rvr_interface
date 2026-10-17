"""Tests for the v.trees.species GRASS addon.

Test groups:
- Interface description validation: required parameter 'treecrowns',
  optional parameter 'ndwi_raster'
- Tree species classification of tree crowns:
  - nDSM: two tree-like blocks (extents 5..9/(center 7) and 15..19
    (center 17), heights 15 and 12), 0 background
  - Spectral bands at each tree crown: red/blue/nir constant, green 110
    vs 40, NDVI high (200) on tree cells, 20 elsewhere
  - treecrowns vector: two crown polygons covering the tree blocks
  - Output: 'treecrowns' vector enriched with the species classification
    columns 'species' (species letter code + optional oak/galley detail)
    and 'speciesINT' (integer species code)

SPDX-FileCopyrightText: (c) 2026 by mundialis GmbH & Co. KG
SPDX-FileCopyrightText: (c) 2026 GRASS Development Team
SPDX-License-Identifier: GPL-2.0-or-later
"""

import grass.script as gs

from conftest import (
    create_vector_areas,
    module_interface,
    require_addon,
    vector_exists,
)


def _setup_inputs(xy_session, tmp_path):
    gs.run_command(
        "r.mapcalc",
        expression=(
            "ndsm = if(row() >= 5 && row() <= 9 && col() >= 5 && col() <= 9, 15, "
            "if(row() >= 15 && row() <= 19 && col() >= 15 && col() <= 19, 12, 0))"
        ),
        env=xy_session.env,
        overwrite=True,
    )
    gs.run_command(
        "r.mapcalc",
        expression=(
            "ndvi = if(ndsm > 1, 200, 20); "
            "red = 100; "
            "blue = 90; "
            "nir = 140"
        ),
        env=xy_session.env,
        overwrite=True,
    )
    gs.run_command(
        "r.mapcalc",
        expression="green = if(ndsm > 1, 110, 40)",
        env=xy_session.env,
        overwrite=True,
    )
    create_vector_areas(
        xy_session,
        tmp_path,
        "treecrowns",
        [(4, 4, 10, 10), (14, 14, 20, 20)],
    )


def test_interface(xy_session):
    require_addon("v.trees.species")
    interface = module_interface("v.trees.species", xy_session)
    assert interface["treecrowns"]
    assert not interface["ndwi_raster"]


def test_species(xy_session, tmp_path):
    _setup_inputs(xy_session, tmp_path)
    gs.run_command(
        "v.trees.species",
        red_raster="red",
        green_raster="green",
        blue_raster="blue",
        nir_raster="nir",
        ndvi_raster="ndvi",
        ndsm="ndsm",
        treecrowns="treecrowns",
        nprocs=1,
        env=xy_session.env,
        quiet=True,
    )
    assert vector_exists(xy_session, "treecrowns")
    columns = gs.vector_columns("treecrowns", env=xy_session.env)
    assert "species" in columns
    assert "speciesINT" in columns

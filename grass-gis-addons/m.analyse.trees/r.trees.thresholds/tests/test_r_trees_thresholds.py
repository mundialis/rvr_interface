"""Tests for the r.trees.thresholds GRASS addon.

Test groups:
- Interface description validation: required parameter 'ndsm_threshold',
  optional parameter 'forest_column'
- Automatic NDVI/NIR threshold estimation from forestry reference data:
  - nDSM: checkerboard, 5 m on odd rows and 0.5 m on even rows, so that
    roughly half the region is 'tree' cells (above ndsm_threshold=1)
  - NDVI: 150 on tree cells, 30 elsewhere; NIR: 160 on tree cells,
    40 elsewhere
  - FNK forest-reference vector covering the whole region
  - The addon estimates NDVI and NIR thresholds to separate the NDVI/NIR
    distribution of tree cells from non-tree cells; the test verifies
    that both thresholds are reported in the standard output

SPDX-FileCopyrightText: (c) 2026 by mundialis GmbH & Co. KG
SPDX-FileCopyrightText: (c) 2026 GRASS Development Team
SPDX-License-Identifier: GPL-2.0-or-later
"""

import grass.script as gs

from conftest import (
    create_vector_areas,
    module_interface,
    require_addon,
)


def _setup_inputs(xy_session, tmp_path):
    gs.run_command(
        "r.mapcalc",
        expression="ndsm = if(row() % 2 == 0, 0.5, 5)",
        env=xy_session.env,
        overwrite=True,
    )
    gs.run_command(
        "r.mapcalc",
        expression="ndvi = if(ndsm > 1, 150, 30)",
        env=xy_session.env,
        overwrite=True,
    )
    gs.run_command(
        "r.mapcalc",
        expression="nir = if(ndsm > 1, 160, 40)",
        env=xy_session.env,
        overwrite=True,
    )
    create_vector_areas(xy_session, tmp_path, "fnk", [(0, 0, 30, 30)])


def test_interface(xy_session):
    require_addon("r.trees.thresholds")
    interface = module_interface("r.trees.thresholds", xy_session)
    assert interface["ndsm_threshold"]
    assert not interface["forest_column"]


def test_thresholds(xy_session, tmp_path):
    _setup_inputs(xy_session, tmp_path)
    out = gs.read_command(
        "r.trees.thresholds",
        forest="fnk",
        nir_raster="nir",
        ndvi_raster="ndvi",
        ndsm="ndsm",
        ndsm_threshold=1,
        nprocs=1,
        env=xy_session.env,
    )
    assert "NDVI threshold" in out
    assert "NIR threshold" in out

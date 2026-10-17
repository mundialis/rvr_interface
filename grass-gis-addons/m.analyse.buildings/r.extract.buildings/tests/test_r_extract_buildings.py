"""Tests for the r.extract.buildings GRASS addon and its worker.

Test groups:
- Interface description validation: required parameters 'fnk_column' and
  'min_size', both for r.extract.buildings and its worker
- Building extraction from normalized digital surface model:
  - nDSM with several stepped building blocks (height 4..8, one per
    6-column strip) inside the 2..27 cell box, 0 outside, built
    row/col-wise so that r.trees-like step functions act on whole tiles
  - NDVI raster: low (20) on building cells (ndsm > 2), high (200) on
    ground, so that NDVI is *below* the threshold on buildings
  - FNK (official building footprint) vector with attribute column
    'code_2020'
  - Output: 'buildings' vector of detected roof polygons with areas > 0
- Worker-parsed output stream: the run must NOT use quiet=True, because
  the worker modules would then suppress the "Output is: <map>" message
  that the parent script parses

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
    vector_info,
)


def _setup_inputs(xy_session, tmp_path):
    tools = xy_session.tools
    gs.run_command(
        "r.mapcalc",
        expression="ndsm = if(row() > 2 && row() < 27 && col() > 2 && col() < 27, 4 + int((col() - 3) / 6), 0)",
        env=xy_session.env,
        overwrite=True,
    )
    tools.r_mapcalc(expression="ndvi = if(ndsm > 2, 20, 200)")
    create_vector_areas(
        xy_session,
        tmp_path,
        "fnk",
        [(0, 0, 30, 30)],
        props={1: {"code_2020": 1}},
    )
    return "ndsm", "ndvi"


def test_interface():
    require_addon("r.extract.buildings")
    require_addon("r.extract.buildings.worker")


def test_interface_params(xy_session):
    interface = module_interface("r.extract.buildings", xy_session)
    assert interface["fnk_column"]
    assert interface["min_size"]


def test_extract_buildings(xy_session, tmp_path):
    ndsm, ndvi = _setup_inputs(xy_session, tmp_path)
    # NOTE: no quiet=True here! r.extract.buildings spawns worker modules
    # and parses their message stream for the "Output is: <map>" line; the
    # workers inherit GRASS_VERBOSE=0 from --quiet and would then suppress
    # exactly that message, so the parsing fails.
    gs.run_command(
        "r.extract.buildings",
        ndsm=ndsm,
        ndvi_raster=ndvi,
        fnk_vector="fnk",
        fnk_column="code_2020",
        min_size=1,
        max_fd=2.5,
        used_thresh="ndvi_thresh",
        ndvi_thresh=145,
        output="buildings",
        tile_size=1000,
        nprocs=1,
        env=xy_session.env,
    )
    assert vector_exists(xy_session, "buildings")
    assert vector_info(xy_session, "buildings")["areas"] > 0

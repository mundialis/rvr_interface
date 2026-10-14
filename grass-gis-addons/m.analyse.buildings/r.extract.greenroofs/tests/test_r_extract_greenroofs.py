"""Tests for the r.extract.greenroofs GRASS addon.

Test groups:
- Interface description validation: required parameters 'used_thresh' and
  'min_veg_size', optional parameter 'fnk'
- Green-roof extraction from building outlines and spectral data:
  - nDSM: flat 8 m block inside the 2..27 cell box, 0 outside
  - NDVI: high (200) on building cells (ndsm > 2), low (20) outside
  - Red/Green/Blue bands: elevated values on the building block, low (30)
    on the ground, so the whole building is vegetated
  - building_outlines vector covering the nDSM block
  - Outputs: 'green_roofs' vector with vegetation patches (areas > 0) and
    'buildings_with_green_roofs' vector of the updated buildings

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
    gs.run_command(
        "r.mapcalc",
        expression=(
            "ndsm = if(row() > 2 && row() < 27 && col() > 2 && col() < 27, 8, 0)"
        ),
        env=xy_session.env,
        overwrite=True,
    )
    gs.run_command(
        "r.mapcalc",
        expression="ndvi = if(ndsm > 2, 200, 20)",
        env=xy_session.env,
        overwrite=True,
    )
    gs.run_command(
        "r.mapcalc",
        expression=(
            "red = if(ndsm > 2, 100, 30); "
            "green = if(ndsm > 2, 120, 30); "
            "blue = if(ndsm > 2, 100, 30)"
        ),
        env=xy_session.env,
        overwrite=True,
    )
    create_vector_areas(
        xy_session, tmp_path, "building_outlines", [(2, 2, 27, 27)]
    )


def test_interface(xy_session):
    require_addon("r.extract.greenroofs")
    require_addon("r.extract.greenroofs.worker")
    interface = module_interface("r.extract.greenroofs", xy_session)
    assert interface["used_thresh"]
    assert interface["min_veg_size"]
    assert not interface["fnk"]


def test_greenroofs(xy_session, tmp_path):
    _setup_inputs(xy_session, tmp_path)
    gs.run_command(
        "r.extract.greenroofs",
        ndsm="ndsm",
        ndvi="ndvi",
        red="red",
        green="green",
        blue="blue",
        buildings="building_outlines",
        used_thresh="gb_thresh",
        gb_thresh=10,
        min_veg_size=1,
        min_veg_proportion=1,
        output_buildings="buildings_with_green_roofs",
        output_vegetation="green_roofs",
        tile_size=1000,
        nprocs=1,
        env=xy_session.env,
        quiet=True,
    )
    assert vector_exists(xy_session, "green_roofs")
    assert vector_info(xy_session, "green_roofs")["areas"] > 0
    assert vector_exists(xy_session, "buildings_with_green_roofs")

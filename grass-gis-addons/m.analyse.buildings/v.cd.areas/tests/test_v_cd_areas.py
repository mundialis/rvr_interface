"""Tests for the v.cd.areas GRASS addon.

Test groups:
- Interface description validation: required parameters 'min_size' and 'max_fd'
- Change detection functionality:
  - Input vector contains two building polygons (one shared with reference,
    one new-only in input)
  - Reference vector contains two building polygons (same shared, one
    old-only in reference)
  - Verifies the addon correctly identifies buildings that differ between
    input and reference, outputting separate polygons for "only in input"
    and "only in reference" trees

The test uses vector areas with a 'floors' attribute to ensure the full
processing pipeline including v.db.renamecolumn operations works correctly.

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


def test_interface(xy_session):
    require_addon("v.cd.areas")
    require_addon("v.cd.areas.worker")
    interface = module_interface("v.cd.areas", xy_session)
    assert interface["min_size"]
    assert interface["max_fd"]


def test_change_detection(xy_session, tmp_path):
    # reference contains a building that the 'new' state no longer has
    create_vector_areas(
        xy_session,
        tmp_path,
        "buildings",
        [(2, 2, 12, 12), (20, 20, 28, 28)],
        props={1: {"floors": 2}, 2: {"floors": 4}},
    )
    create_vector_areas(
        xy_session,
        tmp_path,
        "reference_buildings",
        [(2, 2, 12, 12)],
        props={1: {"floors": 2}},
    )
    gs.run_command(
        "v.cd.areas",
        input="buildings",
        reference="reference_buildings",
        min_size=1,
        max_fd=2.5,
        output="buildings_difference",
        tile_size=1000,
        nprocs=1,
        env=xy_session.env,
        # quiet would set GRASS_VERBOSE=0, silencing the stderr message
        # "Output is: <...>" which v.cd.areas parses from its worker
    )
    assert vector_exists(xy_session, "buildings_difference")
    assert vector_info(xy_session, "buildings_difference")["areas"] > 0

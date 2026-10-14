"""Tests for the v.trees.param GRASS addon.

Test groups:
- Interface description validation: required parameters 'treecrowns',
  'treeparamset' and 'distance_tree'
- Tree parameter calculation:
  - nDSM: two tree-like blocks (centers (6,6)/(16,16), extents 4..8 and
    14..18, heights 15 and 12), 0 background
  - NDVI: high (200) on tree cells (ndsm > 1), 20 elsewhere
  - treecrowns vector: two crown polygons covering the tree blocks
  - reference_buildings vector and parcels line to compute distances
  - Parameters requested: height, area, ndvi
  - Output: 'treecrowns' vector enriched with the computed columns
    'height_p95', 'height_max', 'area_sqm' and 'ndvi_av' added by the
    worker

SPDX-FileCopyrightText: (c) 2026 by mundialis GmbH & Co. KG
SPDX-FileCopyrightText: (c) 2026 GRASS Development Team
SPDX-License-Identifier: GPL-2.0-or-later
"""

import grass.script as gs

from conftest import (
    create_vector_areas,
    create_vector_lines,
    module_interface,
    require_addon,
    vector_exists,
)


def test_interface(xy_session):
    require_addon("v.trees.param")
    require_addon("v.trees.param.worker")
    interface = module_interface("v.trees.param", xy_session)
    assert interface["treecrowns"]
    assert interface["treeparamset"]
    assert interface["distance_tree"]


def test_parameters(xy_session, tmp_path):
    gs.run_command(
        "r.mapcalc",
        expression=(
            "ndsm = if(row() >= 4 && row() <= 8 && col() >= 4 && col() <= 8, 15, "
            "if(row() >= 14 && row() <= 18 && col() >= 14 && col() <= 18, 12, 0))"
        ),
        env=xy_session.env,
        overwrite=True,
    )
    gs.run_command(
        "r.mapcalc",
        expression="ndvi = if(ndsm > 1, 200, 20)",
        env=xy_session.env,
        overwrite=True,
    )
    create_vector_areas(
        xy_session,
        tmp_path,
        "treecrowns",
        [(2, 2, 10, 10), (12, 12, 20, 20)],
    )
    create_vector_areas(
        xy_session, tmp_path, "reference_buildings", [(2, 2, 20, 20)]
    )
    create_vector_lines(xy_session, tmp_path, "parcels", [[(0, 22), (30, 22)]])
    gs.run_command(
        "v.trees.param",
        treecrowns="treecrowns",
        ndsm="ndsm",
        ndvi="ndvi",
        buildings="reference_buildings",
        parcels="parcels",
        treeparamset="height,area,ndvi",
        distance_building=10,
        distance_parcel=10,
        distance_tree=10,
        nprocs=1,
        env=xy_session.env,
        quiet=True,
    )
    assert vector_exists(xy_session, "treecrowns")
    columns = gs.vector_columns("treecrowns", env=xy_session.env)
    # height and area columns are added by the worker
    assert "height_p95" in columns
    assert "height_max" in columns
    assert "area_sqm" in columns
    assert "ndvi_av" in columns

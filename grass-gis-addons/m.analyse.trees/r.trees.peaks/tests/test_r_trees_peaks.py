"""Tests for the r.trees.peaks GRASS addon.

Test groups:
- Interface description validation: required parameter 'forms_res',
  optional parameter 'tile_size'
- Tree crown extraction from nDSM:
  - nDSM: two tree-like disks, centers (10,10) and (20,20), radii ~3
    cells, heights 15 and 12, 0 background
  - study_area vector covering the whole 30x30 region
  - Outputs: 'tree_peaks' raster with the detected peaks and ridges,
    'nearest_tree' raster holding the unique ID of the nearest tree crown
    (computed with r.cost), and 'ndsm_slope' raster computed internally

SPDX-FileCopyrightText: (c) 2026 by mundialis GmbH & Co. KG
SPDX-FileCopyrightText: (c) 2026 GRASS Development Team
SPDX-License-Identifier: GPL-2.0-or-later
"""

import grass.script as gs

from conftest import (
    create_vector_areas,
    module_interface,
    raster_exists,
    require_addon,
)


def _setup_inputs(xy_session, tmp_path):
    gs.run_command(
        "r.mapcalc",
        expression=(
            "ndsm = if((row() - 10) * (row() - 10) + (col() - 10) * (col() - 10) < 9, 15, "
            "if((row() - 20) * (row() - 20) + (col() - 20) * (col() - 20) < 9, 12, 0))"
        ),
        env=xy_session.env,
        overwrite=True,
    )
    create_vector_areas(xy_session, tmp_path, "study_area", [(0, 0, 30, 30)])


def test_interface(xy_session):
    require_addon("r.trees.peaks")
    interface = module_interface("r.trees.peaks", xy_session)
    assert interface["forms_res"]
    assert not interface["tile_size"]


def test_peaks(xy_session, tmp_path):
    _setup_inputs(xy_session, tmp_path)
    gs.run_command(
        "r.trees.peaks",
        area="study_area",
        ndsm="ndsm",
        forms_res=0.8,
        nearest="nearest_tree",
        peaks="tree_peaks",
        slope="ndsm_slope",
        tile_size=1000,
        nprocs=1,
        env=xy_session.env,
        quiet=True,
    )
    assert raster_exists(xy_session, "nearest_tree")
    assert raster_exists(xy_session, "tree_peaks")
    assert raster_exists(xy_session, "ndsm_slope")

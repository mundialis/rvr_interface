"""Tests for the r.trees.postprocess GRASS addon (neural network mode).

Test groups:
- Interface description validation: required parameter 'area_threshold',
  optional parameter 'ndsm'
- Post-processing of tree detections in neural network style:
  - tree_pixels raster from an NN classification: class 0 inside the
    8..16 cell box, NULL elsewhere
  - nearest and peaks rasters covering the same tree cells (values 1
    and 2); both were produced by an upstream NN/r.trees.peaks step
  - -n flag: NN mode, no additional nDSM-based filtering
  - Outputs: 'tree_objects' raster (clumped tree objects) and
    'tree_objects' vector (polygonized objects with areas > 0)

SPDX-FileCopyrightText: (c) 2026 by mundialis GmbH & Co. KG
SPDX-FileCopyrightText: (c) 2026 GRASS Development Team
SPDX-License-Identifier: GPL-2.0-or-later
"""

import grass.script as gs

from conftest import (
    module_interface,
    raster_exists,
    require_addon,
    vector_exists,
    vector_info,
)


def _setup_inputs(xy_session):
    # neural-network style mode: trees have class 0 in the tree pixel map
    gs.run_command(
        "r.mapcalc",
        expression=(
            "tree_pixels = if(row() > 8 && row() < 16 && col() > 8 && col() < 16, 0, null())"
        ),
        env=xy_session.env,
        overwrite=True,
    )
    gs.run_command(
        "r.mapcalc",
        expression=(
            "nearest = if(tree_pixels == 0, 1, null()); "
            "peaks = if(tree_pixels == 0, 2, null())"
        ),
        env=xy_session.env,
        overwrite=True,
    )


def test_interface(xy_session):
    require_addon("r.trees.postprocess")
    interface = module_interface("r.trees.postprocess", xy_session)
    assert interface["area_threshold"]
    assert not interface["ndsm"]


def test_postprocess_nn(xy_session):
    _setup_inputs(xy_session)
    gs.run_command(
        "r.trees.postprocess",
        tree_pixels="tree_pixels",
        nearest="nearest",
        peaks="peaks",
        area_threshold=1,
        trees_raster="tree_objects",
        trees_vector="tree_objects",
        nprocs=1,
        flags="n",
        env=xy_session.env,
        quiet=True,
    )
    assert raster_exists(xy_session, "tree_objects")
    assert vector_exists(xy_session, "tree_objects")
    assert vector_info(xy_session, "tree_objects")["areas"] > 0

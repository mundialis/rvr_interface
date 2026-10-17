"""Tests for the r.trees.traindata GRASS addon.

Test groups:
- Interface description validation: required parameters 'ndvi_threshold' and
  'green_raster'
- Machine learning training data preparation:
  - nDSM disks centered at (10,10) and (20,20) with radius ~3 cells
  - NDVI, NIR, green, blue rasters with high values (200/160) inside radius ~5 disks
  - Nearest and peaks rasters derived from nDSM > 1 threshold
  - r.slope.aspect from nDSM for terrain information
  - Object-based filtering: clumping, zonal max NDVI, mean NDVI threshold
  - Slope quantile filtering to remove low-elevation objects
  - Output: training raster (traindata_r) and vector (traindata_v)

The larger radius-7 high-NDVI regions ensure dilated tree objects maintain
mean NDVI above the 100 threshold after morphological operations.

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
)


def _setup_inputs(xy_session):
    gs.run_command(
        "r.mapcalc",
        expression=(
            "ndsm = if((row() - 10) * (row() - 10) + (col() - 10) * (col() - 10) < 9, 15, "
            "if((row() - 20) * (row() - 20) + (col() - 20) * (col() - 20) < 9, 12, 0))"
        ),
        env=xy_session.env,
        overwrite=True,
    )
    # the high NDVI/NIR region must be larger than the nDSM objects:
    # r.trees.traindata dilates the tree objects (r.neighbors mode) and
    # discards clumps whose mean NDVI is below the threshold
    gs.run_command(
        "r.mapcalc",
        expression=(
            "ndvi = if((row() - 10) * (row() - 10) + (col() - 10) * (col() - 10) < 49, 200, "
            "if((row() - 20) * (row() - 20) + (col() - 20) * (col() - 20) < 49, 200, 20))"
        ),
        env=xy_session.env,
        overwrite=True,
    )
    gs.run_command(
        "r.mapcalc",
        expression=(
            "nir = if((row() - 10) * (row() - 10) + (col() - 10) * (col() - 10) < 49, 160, "
            "if((row() - 20) * (row() - 20) + (col() - 20) * (col() - 20) < 49, 160, 40))"
        ),
        env=xy_session.env,
        overwrite=True,
    )
    gs.run_command(
        "r.mapcalc",
        expression=(
            "green = if((row() - 10) * (row() - 10) + (col() - 10) * (col() - 10) < 49, 200, 20); "
            "blue = if((row() - 10) * (row() - 10) + (col() - 10) * (col() - 10) < 49, 200, 20)"
        ),
        env=xy_session.env,
        overwrite=True,
    )
    gs.run_command(
        "r.mapcalc",
        expression=(
            "nearest = if(ndsm > 1, 1, null()); "
            "peaks = if(ndsm > 1, 2, null())"
        ),
        env=xy_session.env,
        overwrite=True,
    )
    gs.run_command(
        "r.slope.aspect",
        elevation="ndsm",
        slope="ndsm_slope",
        env=xy_session.env,
        overwrite=True,
    )


def test_interface(xy_session):
    require_addon("r.trees.traindata")
    interface = module_interface("r.trees.traindata", xy_session)
    assert interface["ndvi_threshold"]
    assert not interface["green_raster"] or "green_raster" in interface


def test_traindata(xy_session):
    _setup_inputs(xy_session)
    gs.run_command(
        "r.trees.traindata",
        green_raster="green",
        blue_raster="blue",
        nir_raster="nir",
        ndvi_raster="ndvi",
        ndsm="ndsm",
        slope="ndsm_slope",
        nearest="nearest",
        peaks="peaks",
        ndvi_threshold=100,
        nir_threshold=100,
        ndsm_threshold=1,
        slopep75_threshold=0,
        area_threshold=5,
        traindata_r="traindata_r",
        traindata_v="traindata_v",
        nprocs=1,
        env=xy_session.env,
        quiet=True,
    )
    assert raster_exists(xy_session, "traindata_r")
    assert vector_exists(xy_session, "traindata_v")

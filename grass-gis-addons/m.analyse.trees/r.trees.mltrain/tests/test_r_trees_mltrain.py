"""Tests for the r.trees.mltrain GRASS addon.

Test groups:
- Interface description validation: required parameter 'ndvi_threshold'
- Machine learning model training:
  - Synthetic tree presence raster (value 2 in 8-12 cell patch, null elsewhere)
  - NDVI with a high-value ring (value 180) around trees and high interior (200)
  - RGBNIR bands conditioned on NDVI threshold
  - nDSM with explicit 0 values outside trees to ensure full coverage
  - Nearest pixel raster covering both real and false tree locations
  - RandomForest classification model trained from the input georeferenced data
  - Output: trained model saved to gzip file

The geometry ensures proper class separation: tree cells (val 2) and background
(false_trees, notrees) cells (val 1) for binary classification.

SPDX-FileCopyrightText: (c) 2026 by mundialis GmbH & Co. KG
SPDX-FileCopyrightText: (c) 2026 GRASS Development Team
SPDX-License-Identifier: GPL-2.0-or-later
"""

import grass.script as gs

from conftest import module_interface, require_addon


def _setup_inputs(xy_session):
    gs.run_command(
        "r.mapcalc",
        expression=(
            "trees = if(row() >= 8 && row() <= 12 && col() >= 8 && col() <= 12, 2, null())"
        ),
        env=xy_session.env,
        overwrite=True,
    )
    # ring of high NDVI around the trees -> "false trees"
    gs.run_command(
        "r.mapcalc",
        expression=(
            "ndvi = if(row() >= 8 && row() <= 12 && col() >= 8 && col() <= 12, 200, "
            "if(row() >= 6 && row() <= 14 && col() >= 6 && col() <= 14, 180, 30))"
        ),
        env=xy_session.env,
        overwrite=True,
    )
    gs.run_command(
        "r.mapcalc",
        expression=(
            # assignments may not reference maps created in this same run
            # (r.mapcalc segfaults on chained in-run references)
            "red = if(ndvi > 100, 100, 40)"
        ),
        env=xy_session.env,
        overwrite=True,
    )
    gs.run_command(
        "r.mapcalc",
        expression=("green = if(ndvi > 100, 100, 40)"),
        env=xy_session.env,
        overwrite=True,
    )
    gs.run_command(
        "r.mapcalc",
        expression=("blue = if(ndvi > 100, 100, 40)"),
        env=xy_session.env,
        overwrite=True,
    )
    gs.run_command(
        "r.mapcalc",
        expression=("nir = if(ndvi > 100, 100, 40)"),
        env=xy_session.env,
        overwrite=True,
    )
    gs.run_command(
        "r.mapcalc",
        expression=(
            "ndsm = if(isnull(trees), 0, if(trees == 2, 15, 0)); " "slope = 0"
        ),
        env=xy_session.env,
        overwrite=True,
    )
    gs.run_command(
        "r.mapcalc",
        # nearest pixel NDVI covers the whole high-NDVI area (trees and the
        # high-NDVI ring around them which r.trees.mltrain uses as
        # "false trees"), not only the tree cells themselves
        expression="nearest = if(ndvi > 130, 1, null())",
        env=xy_session.env,
        overwrite=True,
    )


def test_interface(xy_session):
    require_addon("r.trees.mltrain")
    interface = module_interface("r.trees.mltrain", xy_session)
    assert interface["ndvi_threshold"] or "ndvi_threshold" in interface


def test_mltrain(xy_session, tmp_path):
    _setup_inputs(xy_session)
    model_file = tmp_path / "model.gz"
    gs.run_command(
        "r.trees.mltrain",
        red_raster="red",
        green_raster="green",
        blue_raster="blue",
        nir_raster="nir",
        ndvi_raster="ndvi",
        ndsm="ndsm",
        slope="slope",
        nearest="nearest",
        ndvi_threshold=130,
        trees_raw_r="trees",
        num_samples=10,
        group="ml_input",
        save_model=str(model_file),
        nprocs=1,
        env=xy_session.env,
        quiet=True,
    )
    assert model_file.is_file()
    assert model_file.stat().st_size > 0

"""Tests for the r.trees.mlapply GRASS addon.

Test groups:
- Interface description validation: required parameter 'model', optional
  'tile_size'
- Machine learning model application:
  - Binary tree presence raster with two classes (2=trees in 8-12 patch,
    1=background elsewhere)
  - Full spectral band stack (red, green, blue, nir, ndvi, ndwi, ndgb,
    ndsm, slope) conditioned on tree class
  - Training data prepared via i.group
  - RandomForest model trained using r.learn.train
  - Model applied to classify the study area via worker processes
  - Output: classification raster ('tree_pixels') where value 2 indicates
    detected trees

This is an end-to-end test exercising the full machine learning pipeline
from feature creation through model training and inference.

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
        expression="trees = if(row() >= 8 && row() <= 12 && col() >= 8 && col() <= 12, 2, 1)",
        env=xy_session.env,
        overwrite=True,
    )
    gs.run_command(
        "r.mapcalc",
        expression=(
            "red = if(trees == 2, 100, 40); "
            "green = if(trees == 2, 120, 40); "
            "blue = if(trees == 2, 100, 40); "
            "nir = if(trees == 2, 140, 40); "
            "ndvi = if(trees == 2, 200, 30); "
            "ndsm = if(trees == 2, 15, 0); "
            "slope = 0; "
            "ndwi = if(trees == 2, 0.3, 0.1); "
            "ndgb = if(trees == 2, 0.2, 0.1)"
        ),
        env=xy_session.env,
        overwrite=True,
    )
    create_vector_areas(xy_session, tmp_path, "study_area", [(0, 0, 30, 30)])


def _train_model(xy_session, model_file):
    gs.run_command(
        "i.group",
        group="ml_input",
        input="red,green,blue,nir,ndvi,ndwi,ndgb,ndsm,slope",
        env=xy_session.env,
        quiet=True,
    )
    gs.run_command(
        "r.learn.train",
        group="ml_input",
        training_map="trees",
        save_model=str(model_file),
        model_name="RandomForestClassifier",
        cv=5,
        flags="f",
        n_jobs=1,
        min_samples_leaf=2,
        n_estimators=10,
        max_depth=5,
        env=xy_session.env,
        quiet=True,
    )


def test_interface(xy_session):
    require_addon("r.trees.mlapply")
    require_addon("r.trees.mlapply.worker")
    interface = module_interface("r.trees.mlapply", xy_session)
    assert interface["model"]
    assert not interface["tile_size"]


def test_mlapply(xy_session, tmp_path):
    _setup_inputs(xy_session, tmp_path)
    model_file = tmp_path / "model.gz"
    _train_model(xy_session, model_file)
    gs.run_command(
        "r.trees.mlapply",
        area="study_area",
        group="ml_input",
        model=str(model_file),
        output="tree_pixels",
        tile_size=1000,
        nprocs=1,
        env=xy_session.env,
        quiet=True,
    )
    assert raster_exists(xy_session, "tree_pixels")

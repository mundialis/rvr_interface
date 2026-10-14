"""Tests for the r.in.pdal.worker GRASS addon.

Test groups:
- Interface description validation: required parameter 'res', optional
  parameter 'new_mapset'
- LAZ point cloud import as raster DSM:
  - Synthetic 5x5 point cloud (X/Y 0..4, Z = row + col + 1, so heights
    1..9) written as CSV and converted to a LAZ file with the 'pdal'
    pipeline reader (skipped if the pdal CLI is not available)
  - Worker imports the LAZ into a raster at 1 m resolution (flags 'on')
  - Output: 'dsm_from_laz' raster with a maximum cell value >= 8,
    verifying the highest point is preserved

SPDX-FileCopyrightText: (c) 2026 by mundialis GmbH & Co. KG
SPDX-FileCopyrightText: (c) 2026 GRASS Development Team
SPDX-License-Identifier: GPL-2.0-or-later
"""

import json
import shutil
import subprocess

import pytest
import grass.script as gs

from conftest import module_interface, raster_exists, require_addon


@pytest.fixture(scope="module")
def addon():
    require_addon("r.in.pdal.worker")
    return "r.in.pdal.worker"


def _write_laz(tmp_path, name="points.laz"):
    """Generate a small LAZ file with pdal from a synthetic point cloud."""
    pdal = shutil.which("pdal")
    if not pdal:
        pytest.skip("pdal CLI not available")
    csv_path = tmp_path / "points.csv"
    with open(csv_path, "w") as file:
        file.write("X,Y,Z\n")
        for row in range(5):
            for col in range(5):
                file.write(f"{col},{row},{row + col + 1}\n")
    laz_path = tmp_path / name
    pipeline = {
        "pipeline": [
            {
                "type": "readers.text",
                "filename": str(csv_path),
            },
            {
                "type": "writers.las",
                "filename": str(laz_path),
                "major_version": 1,
                "minor_version": 4,
                "dataformat_id": 6,
            },
        ]
    }
    pipeline_path = tmp_path / "pipeline.json"
    with open(pipeline_path, "w") as file:
        json.dump(pipeline, file)
    subprocess.run(
        [pdal, "pipeline", str(pipeline_path)], check=True, timeout=120
    )
    return laz_path


def test_interface(addon, xy_session):
    interface = module_interface(addon, xy_session)
    assert interface["res"]
    assert not interface["new_mapset"]


def test_pdal_input(addon, xy_session, tmp_path):
    laz_path = _write_laz(tmp_path)
    gs.run_command(
        addon,
        input=str(laz_path),
        output="dsm_from_laz",
        res=1,
        flags="on",
        env=xy_session.env,
        overwrite=True,
    )
    assert raster_exists(xy_session, "dsm_from_laz")
    stats = gs.parse_command(
        "r.univar", map="dsm_from_laz", flags="g", env=xy_session.env
    )
    assert float(stats["max"]) >= 8

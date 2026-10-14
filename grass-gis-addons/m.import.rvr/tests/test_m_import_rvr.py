"""Tests for the m.import.rvr GRASS addon (check mode).

Test groups:
- Interface description validation: required parameters 'type' and 'area'
- Check mode with stub input files: verifies that the addon correctly
  validates all required input paths (type, area, dop_dir, dsm_dir, fnk_file)
  and reports success with 'Only the data are checked' message
- Check mode with missing mandatory input: verifies that the addon
  properly reports missing 'fnk_file' as an error

SPDX-FileCopyrightText: (c) 2026 by mundialis GmbH & Co. KG
SPDX-FileCopyrightText: (c) 2026 GRASS Development Team
SPDX-License-Identifier: GPL-2.0-or-later
"""

import subprocess

import pytest

from conftest import module_interface, require_addon


@pytest.fixture(scope="module")
def addon():
    require_addon("m.import.rvr")
    return "m.import.rvr"


def test_interface(addon, xy_session):
    interface = module_interface(addon, xy_session)
    assert interface["type"]
    assert interface["area"]


def test_check_ok(addon, xy_session, tmp_path):
    dop_dir = tmp_path / "dop"
    dsm_dir = tmp_path / "dsm"
    dop_dir.mkdir()
    dsm_dir.mkdir()
    fnk_file = tmp_path / "fnk.geojson"
    fnk_file.write_text('{"type":"FeatureCollection","features":[]}')
    area_file = tmp_path / "area.geojson"
    area_file.write_text('{"type":"FeatureCollection","features":[]}')
    proc = subprocess.run(
        [
            addon,
            "type=buildings analysis",
            f"area={area_file}",
            f"dop_dir={dop_dir}",
            f"dsm_dir={dsm_dir}",
            f"fnk_file={fnk_file}",
            "fnk_column=code_2020",
            "nprocs=1",
            "-c",
        ],
        env=xy_session.env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Only the data are checked" in proc.stderr


def test_check_missing_fnk_data(addon, xy_session, tmp_path):
    dop_dir = tmp_path / "dop"
    dsm_dir = tmp_path / "dsm"
    dop_dir.mkdir()
    dsm_dir.mkdir()
    area_file = tmp_path / "area.geojson"
    area_file.write_text('{"type":"FeatureCollection","features":[]}')
    proc = subprocess.run(
        [
            addon,
            "type=buildings analysis",
            f"area={area_file}",
            f"dop_dir={dop_dir}",
            f"dsm_dir={dsm_dir}",
            "nprocs=1",
            "-c",
        ],
        env=xy_session.env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode != 0
    assert "fnk_file" in proc.stderr

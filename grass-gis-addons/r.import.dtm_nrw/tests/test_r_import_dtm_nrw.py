"""Tests for the r.import.dtm_nrw GRASS addon.

Test groups:
- Interface description validation: required parameter 'output',
  optional parameter 'directory'
- Failure behavior outside the NRW tile grid:
  - Runs the addon in the XY test project (no EPSG code definable, thus
    no way to determine the NRW index tile); the addon must fail with a
    non-zero return code instead of importing garbage data
- No data download is performed in these tests (no internet access to
  the NRW WMS/WMTS services assumed)

SPDX-FileCopyrightText: (c) 2026 by mundialis GmbH & Co. KG
SPDX-FileCopyrightText: (c) 2026 GRASS Development Team
SPDX-License-Identifier: GPL-2.0-or-later
"""

import subprocess

import pytest

from conftest import module_interface, require_addon


@pytest.fixture(scope="module")
def addon():
    require_addon("r.import.dtm_nrw")
    return "r.import.dtm_nrw"


def test_interface(addon, xy_session):
    interface = module_interface(addon, xy_session)
    assert interface["output"]
    assert not interface["directory"]


def test_fails_outside_nrw(addon, xy_session, tmp_path):
    """The addon localizes the region with pyproj; in the XY test project
    no EPSG code can be determined so it must fail cleanly.
    """
    proc = subprocess.run(
        [addon, "output=out", f"directory={tmp_path}"],
        env=xy_session.env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode != 0

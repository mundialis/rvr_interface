"""Tests for the r.import.ndsm_nrw GRASS addon.

Test groups:
- Interface description validation: required parameters 'dsm' and
  'output_ndsm', presence of the optional 'dtm' parameter
- nDSM calculation (DSM minus DTM):
  - DSM: flat 5 m surface with an elevated 10 m block in the 10..20 cell
    box (so the block reaches 15 m)
  - DTM: flat 5 m surface
  - Outputs: 'ndsm' raster (block ~10 m, background ~0 m) and 'dtm_out';
    verifies r.univar stats max > 8 and min > -2
- Error handling for missing required options: calling the module without
  'dsm' raises CalledModuleError

SPDX-FileCopyrightText: (c) 2026 by mundialis GmbH & Co. KG
SPDX-FileCopyrightText: (c) 2026 GRASS Development Team
SPDX-License-Identifier: GPL-2.0-or-later
"""

import pytest
import grass.script as gs
from grass.exceptions import CalledModuleError

from conftest import module_interface, raster_exists, require_addon

MODULE = "r.import.ndsm_nrw"


def test_interface(xy_session):
    require_addon(MODULE)
    params = module_interface(MODULE, xy_session)
    assert params["dsm"]
    assert params["output_ndsm"]
    assert "dtm" in params


def test_ndsm_calculation(xy_session):
    """nDSM is computed as DSM - DTM when a DTM raster is given."""
    require_addon(MODULE)
    tools = xy_session.tools
    env = xy_session.env

    # DSM: a flat surface with an elevated block in the middle
    tools.r_mapcalc(
        expression="dsm = 5 + if(row() > 10 && row() < 20 && col() > 10 && col() < 20, 10, 0)"
    )
    tools.r_mapcalc(expression="dtm = 5")
    gs.run_command(
        MODULE,
        dsm="dsm",
        dtm="dtm",
        output_ndsm="ndsm",
        output_dtm="dtm_out",
        env=env,
    )
    assert raster_exists(xy_session, "ndsm")
    assert raster_exists(xy_session, "dtm_out")

    stats = tools.r_univar(map="ndsm", format="json")
    # the elevated block of ~10 m must be visible in the nDSM
    assert float(stats["max"]) > 8
    assert float(stats["min"]) > -2


def test_requires_dsm_and_output(xy_session):
    """Missing required options must be reported."""
    require_addon(MODULE)
    env = xy_session.env
    with pytest.raises(CalledModuleError):
        gs.run_command(MODULE, output_ndsm="ndsm", env=env)

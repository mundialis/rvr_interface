"""Shared fixtures for the GRASS GIS addon tests of this repository.

The tests follow the GRASS GIS testing conventions described in
https://github.com/OSGeo/grass/blob/main/doc/development/testing.md
(pytest tests live in a ``tests`` directory next to the code they test
and use an active GRASS session set up in a ``conftest.py`` fixture).

To run the tests you need an installed GRASS GIS with every addon of this
repository installed, plus the four external addons they call:

    r.learn.train        used by r.trees.mlapply
    r.learn.ml2          supplies the rlearnlib helper that r.learn.train needs
    v.centerpoint        used by v.trees.param (compiled)
    r.dtm.import.nw      used by m.import.rvr; lives in the differently named
                         repository https://github.com/mundialis/r.dem.import

GRASS GIS 8.5 or newer is required because the fixtures use ``grass.tools``.

Install the addons of this repository with:

    for addon in $(ls -1 grass-gis-addons/*/Makefile | cut -d/ -f2) ; do
        g.extension extension=$addon url=$PWD/grass-gis-addons/$addon
    done
    for addon in r.learn.train r.learn.ml2 v.centerpoint ; do
        g.extension extension=$addon
    done
    g.extension extension=r.dtm.import.nw \\
        url=https://github.com/mundialis/r.dem.import

Note that ``g.extension`` reports a failed installation with a warning but
still exits 0, so check that the addons are really there before concluding
that a test failure is a real failure.

Then run pytest with:

    export PYTHONPATH="$(grass --config python_path):$PYTHONPATH"
    export LD_LIBRARY_PATH="$(grass --config path)/lib:$LD_LIBRARY_PATH"
    pytest grass-gis-addons/
"""

import json
import os
import shutil
import xml.etree.ElementTree as ET

import pytest

import grass.script as gs
from grass.tools import Tools

# Make installed GRASS GIS addons findable by the module subprocesses
# spawned by the tests. The core GRASS modules are already added to the
# session PATH by ``gs.setup.init()``, the addons are not.
_GRASS_ADDON_BASE = os.environ.get(
    "GRASS_ADDON_BASE", os.path.expanduser("~/.grass8/addons")
)
if os.path.isdir(_GRASS_ADDON_BASE):
    os.environ["GRASS_ADDON_BASE"] = _GRASS_ADDON_BASE
    for subdir in ("bin", "scripts"):
        _path = os.path.join(_GRASS_ADDON_BASE, subdir)
        if os.path.isdir(_path):
            os.environ["PATH"] = (
                _path + os.pathsep + os.environ.get("PATH", "")
            )


@pytest.fixture
def xy_session(tmp_path):
    """An active GRASS session in a small XY project (function scope).

    An XY project is used because the tests are not about coordinate
    reference systems; the addons treat the project units as meters.

    Returns an object with ``session``, ``tools`` and ``env`` attributes.
    """
    project = tmp_path / "xy_test"
    gs.create_project(project)
    with gs.setup.init(project, env=os.environ.copy()) as session:
        # set a valid region before Tools() so that its cleanup at context
        # exit can restore it
        gs.run_command(
            "g.region", s=0, n=30, w=0, e=30, res=1, env=session.env
        )
        # GRASS wraps long module messages at the terminal width; some
        # addons (e.g. r.extract.buildings) parse the message stream of
        # spawned worker modules, so request unwrapped plain messages.
        session.env["GRASS_INFO_FORMAT"] = "plain"
        with Tools(session=session) as tools:
            _Session = type(
                "_Session",
                (),
                {"session": session, "tools": tools, "env": session.env},
            )
            _instance = _Session()
            yield _instance


def create_vector_areas(session, tmp_path, name, areas, props=None):
    """Create a vector area map from axis-aligned boxes.

    areas: list of (w, s, e, n) tuples.
    props: optional dict mapping cat (1-based) to dict of
           column_name: value; columns are added as attributes.
    """
    features = []
    for idx, (w, s, e, n) in enumerate(areas, start=1):
        ring = [(w, s), (e, s), (e, n), (w, n), (w, s)]
        feature = {
            "type": "Feature",
            "properties": {
                "cat": idx,
                **(props.get(idx, {}) if props else {}),
            },
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        }
        features.append(feature)
    geojson = {"type": "FeatureCollection", "features": features}
    path = str(tmp_path / f"{name}.geojson")
    with open(path, "w") as file:
        json.dump(geojson, file)
    # -o: override the projection check since the tests use an XY project
    gs.run_command(
        "v.import",
        input=path,
        output=name,
        flags="o",
        env=session.env,
        quiet=True,
    )


def create_vector_lines(session, tmp_path, name, lines):
    """Create a vector line map from an axis-aligned line segments.

    lines: list of [(x, y), ...] coordinate lists.
    """
    features = []
    for idx, coords in enumerate(lines, start=1):
        feature = {
            "type": "Feature",
            "properties": {"cat": idx},
            "geometry": {"type": "LineString", "coordinates": coords},
        }
        features.append(feature)
    geojson = {"type": "FeatureCollection", "features": features}
    path = str(tmp_path / f"{name}.geojson")
    with open(path, "w") as file:
        json.dump(geojson, file)
    gs.run_command(
        "v.import",
        input=path,
        output=name,
        flags="o",
        env=session.env,
        quiet=True,
    )


def vector_info(session, name):
    """Return vector feature counts (points, lines, boundaries, areas)."""
    return gs.vector_info_topo(name, env=session.env)


def vector_exists(session, name):
    """Check whether a vector map exists in the current mapset."""
    return bool(
        gs.find_file(name=name, element="vector", env=session.env)["file"]
    )


def raster_exists(session, name):
    """Check whether a raster map exists in the current mapset."""
    return bool(
        gs.find_file(name=name, element="cell", env=session.env)["file"]
    )


def module_interface(addon, xy):
    """Return a dict of {parameter name: required} for an addon.

    Queries the addon's ``--interface-description`` which is emitted as
    XML by ``grass.parser()``. Needs an active GRASS session.
    """
    xml = gs.read_command(addon, "--interface-description", env=xy.env)
    root = ET.fromstring(xml)
    return {
        par.get("name"): par.get("required") == "yes"
        for par in root.findall(".//parameter")
        if par.get("name") not in ("overwrite", "verbose", "quiet")
    }


def require_addon(addon):
    """Compile-time check that an addon is installed."""
    assert shutil.which(addon), (
        f"addon <{addon}> is not installed, install it first with "
        "g.extension"
    )

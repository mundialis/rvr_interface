#!/bin/sh

# Run the pytest suites of the addons in this repository.
#
# GRASS 8.5 is required: conftest.py imports grass.tools, which was added in
# 8.5 and does not exist in the 8.3 image used by the installation check.
#
# local test:
#   docker run -it -v .:/src --rm osgeo/grass-gis:releasebranch_8_5-alpine \
#     bash /src/.github/workflows/test_addon_pytests.sh

# fail on non-zero return code from a subprocess
set -e

export PIP_BREAK_SYSTEM_PACKAGES=1

# build dependencies, pytest, and the Python packages the addons need
apk add --no-cache gcc libc-dev linux-headers make musl-dev proj-dev \
    python3-dev py3-scikit-learn py3-pytest py3-psutil py3-requests \
    py3-tqdm pandoc

# the 8.5 image ships neither pip nor py3-pyproj, so bootstrap pip first
if ! command -v pip3 >/dev/null 2>&1 ; then
    wget -qO /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py
    python3 /tmp/get-pip.py --break-system-packages
fi
python3 -m pip install --break-system-packages -r /src/grass-gis-addons/requirements.txt

# compiled addons of this repository
for addon in $(ls -1 /src/grass-gis-addons/*/Makefile | cut -d'/' -f4) ; do
    echo "Installing addon <$addon>..."
    grass --tmp-project XY --exec g.extension $addon url=/src/grass-gis-addons/$addon/
done

# Addons that the addons of this repository call but that are not declared
# anywhere in the repository. Without them the suites fail with
# "module was not found" rather than an assertion error, which makes the
# tests look broken instead of unconfigured.
for addon in r.learn.train r.learn.ml2 v.centerpoint ; do
    echo "Installing addon <$addon>..."
    grass --tmp-project XY --exec g.extension $addon
done

# r.dtm.import.nw lives in a differently named repository; m.import.rvr
# suggests this exact command when the module is missing.
echo "Installing addon <r.dtm.import.nw>..."
grass --tmp-project XY --exec g.extension r.dtm.import.nw \
    url=https://github.com/mundialis/r.dem.import

# g.extension exits 0 even when it prints "Installation failed", so `set -e`
# cannot be trusted here. r.dtm.import.nw in particular installs its module
# but fails to install a shared library directory, and the suites only pass
# because the module itself landed. Check explicitly instead.
#
# Look for what the addon actually installed rather than running it: r.learn.ml2
# ships no module at all, only the etc/r.learn.ml2/rlearnlib helper library.
for addon in r.learn.train r.learn.ml2 v.centerpoint r.dtm.import.nw ; do
    if [ ! -f "/root/.grass8/addons/scripts/$addon" ] &&
       [ ! -f "/root/.grass8/addons/bin/$addon" ] &&
       [ ! -d "/root/.grass8/addons/etc/$addon" ] ; then
        echo "ERROR: required addon <$addon> was not installed" >&2
        exit 1
    fi
done
echo "All required addons are installed."

# v.centerpoint installs into addons/bin, which is not on PATH yet
export PATH="/root/.grass8/addons/bin:$PATH"

export PYTHONPATH="$(grass --config python_path):${PYTHONPATH}"
export LD_LIBRARY_PATH="$(grass --config path)/lib:${LD_LIBRARY_PATH}"

cd /src
python3 -m pytest -v grass-gis-addons/

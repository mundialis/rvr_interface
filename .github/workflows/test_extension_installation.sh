#!/bin/sh

# test script for Alpine docker with GRASS GIS
# local test:
#   docker run -it -v .:/src --rm osgeo/grass-gis:releasebranch_8_3-alpine bash /src/test_extension_installation.sh 

# fail on non-zero return code from a subprocess
set -e

# add dependencies
apk add  --no-cache gcc libc-dev linux-headers make musl-dev proj-dev python3-dev
apk add --no-cache py3-scikit-learn
pip install --upgrade pip
# workaround for broken pyproj release, remove when pyproj 3.6.1 is out
pip3 install pyproj@git+https://github.com/pyproj4/pyproj.git@main
# all other requirements
pip install -r /src/grass-gis-addons/requirements.txt

# loop over existing addons
for addon in $(ls -1 /src/grass-gis-addons/*/Makefile | cut -d'/' -f4) ; do
    echo "Testing installation of addon <$addon>...:"
    grass --tmp-location epsg:25832 --exec g.extension $addon url=/src/grass-gis-addons/$addon/
done

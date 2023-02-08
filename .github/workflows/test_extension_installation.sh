#!/bin/sh

# test script for Alpine docker with GRASS GIS
# local test:
#   docker run -it -v .:/src --rm mundialis/grass-py3-pdal:8.2.1-alpine bash /src/test_extension_installation.sh 

# fail on non-zero return code from a subprocess
set -e

# add dependencies
apk add  --no-cache gcc libc-dev linux-headers make musl-dev proj-dev python3-dev
pip install --upgrade pip
pip install -r /src/grass-gis-addons/requirements.txt

# loop over existing addons
for addon in $(ls -1 /src/grass-gis-addons/*/Makefile | cut -d'/' -f4) ; do
    echo "Testing installation of addon <$addon>...:"
    grass --tmp-location epsg:25832 --exec g.extension $addon url=/src/grass-gis-addons/$addon/
done

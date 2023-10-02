FROM osgeo/grass-gis:releasebranch_8_3-alpine

# is this needed or already set in the base image?
# ---> 
SHELL ["/bin/bash", "-c"]
# set SHELL var to avoid /bin/sh fallback in interactive GRASS GIS sessions
ENV SHELL /bin/bash
ENV LC_ALL "en_US.UTF-8"
ENV GRASS_SKIP_MAPSET_OWNER_CHECK 1

# https://proj.org/usage/environmentvars.html#envvar-PROJ_NETWORK
ENV PROJ_NETWORK=ON
# <---

# install external dependencies
RUN apk add --no-cache gcc make py3-psutil bash musl-dev python3-dev proj-dev
RUN apk add --no-cache py3-scikit-learn
RUN pip3 install py7zr tqdm requests
# workaround for broken pyproj release, remove when pyproj 3.6.1 is out
RUN pip3 install pyproj@git+https://github.com/pyproj4/pyproj.git@main

# install official addons
RUN grass --tmp-location EPSG:4326 --exec g.extension r.mapcalc.tiled -s
RUN grass --tmp-location EPSG:4326 --exec g.extension v.centerpoint -s
RUN grass --tmp-location EPSG:4326 --exec g.extension r.learn.ml2 -s

# install an addon from mundialis
RUN grass --tmp-location EPSG:4326 --exec g.extension v.alkis.buildings.import url=https://github.com/mundialis/v.alkis.buildings.import -s

# install RVR-specific GRASS GIS addons
COPY grass-gis-addons /src/grass-gis-addons

RUN grass --tmp-location EPSG:4326 --exec g.extension r.import.dtm_nrw url=/src/grass-gis-addons/r.import.dtm_nrw -s
RUN grass --tmp-location EPSG:4326 --exec g.extension r.in.pdal.worker url=/src/grass-gis-addons/r.in.pdal.worker -s
RUN grass --tmp-location EPSG:4326 --exec g.extension r.import.ndsm_nrw url=/src/grass-gis-addons/r.import.ndsm_nrw -s
RUN grass --tmp-location EPSG:4326 --exec g.extension m.import.rvr url=/src/grass-gis-addons/m.import.rvr -s
RUN grass --tmp-location EPSG:4326 --exec g.extension m.analyse.trees url=/src/grass-gis-addons/m.analyse.trees -s
RUN grass --tmp-location EPSG:4326 --exec g.extension m.analyse.buildings url=/src/grass-gis-addons/m.analyse.buildings -s
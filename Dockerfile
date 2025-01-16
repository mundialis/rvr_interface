FROM osgeo/grass-gis:8.4.0-ubuntu_wxgui

# Version of GRASS GIS Addons
ENV V_ALKIS_BUILDINGS_IMPORT_VERSION 1.1.0

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

# set GRASS_ADDON_BASE
ENV GRASS_ADDON_BASE=/usr/local/grass84

# install external dependencies
RUN pip3 install py7zr tqdm requests psutil scikit-learn pyproj pandas grass-gis-helpers

# install official addons
RUN grass --tmp-location EPSG:4326 --exec g.extension r.mapcalc.tiled -s
RUN grass --tmp-location EPSG:4326 --exec g.extension v.centerpoint -s
RUN grass --tmp-location EPSG:4326 --exec g.extension r.learn.ml2 -s

# install addons from mundialis
RUN wget https://github.com/mundialis/v.alkis.buildings.import/archive/refs/tags/${V_ALKIS_BUILDINGS_IMPORT_VERSION}.zip \
    && grass --tmp-location EPSG:4326 --exec g.extension v.alkis.buildings.import url=${V_ALKIS_BUILDINGS_IMPORT_VERSION}.zip -s \
    && rm ${V_ALKIS_BUILDINGS_IMPORT_VERSION}.zip

RUN grass --tmp-location EPSG:4326 --exec g.extension m.neural_network url=https://github.com/mundialis/m.neural_network -s

# install RVR-specific GRASS GIS addons
COPY grass-gis-addons /src/grass-gis-addons

RUN grass --tmp-location EPSG:4326 --exec g.extension r.import.dtm_nrw url=/src/grass-gis-addons/r.import.dtm_nrw -s
RUN grass --tmp-location EPSG:4326 --exec g.extension r.in.pdal.worker url=/src/grass-gis-addons/r.in.pdal.worker -s
RUN grass --tmp-location EPSG:4326 --exec g.extension r.import.ndsm_nrw url=/src/grass-gis-addons/r.import.ndsm_nrw -s
RUN grass --tmp-location EPSG:4326 --exec g.extension m.import.rvr url=/src/grass-gis-addons/m.import.rvr -s
RUN grass --tmp-location EPSG:4326 --exec g.extension m.analyse.trees url=/src/grass-gis-addons/m.analyse.trees -s
RUN grass --tmp-location EPSG:4326 --exec g.extension m.analyse.buildings url=/src/grass-gis-addons/m.analyse.buildings -s
RUN grass --tmp-location EPSG:4326 --exec g.extension r.dem.import url=https://github.com/mundialis/r.dem.import -s

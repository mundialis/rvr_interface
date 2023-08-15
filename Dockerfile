FROM osgeo/grass-gis:releasebranch_8_3-alpine

# install external dependencies
RUN apk add --no-cache gcc make py3-psutil bash musl-dev python3-dev proj-dev
RUN apk add --no-cache py3-scikit-learn
RUN pip3 install py7zr tqdm requests
RUN pip3 install pyproj@git+https://github.com/pyproj4/pyproj.git@main

# install RVR-specific GRASS GIS addons
RUN grass --tmp-location EPSG:4326 --exec g.extension r.import.dtm_nrw url=grass-gis-addons/r.import.dtm_nrw -s
RUN grass --tmp-location EPSG:4326 --exec g.extension r.in.pdal.worker url=grass-gis-addons/r.in.pdal.worker -s
RUN grass --tmp-location EPSG:4326 --exec g.extension r.import.ndsm_nrw url=grass-gis-addons/r.import.ndsm_nrw -s
RUN grass --tmp-location EPSG:4326 --exec g.extension m.import.rvr url=grass-gis-addons/m.import.rvr -s
RUN grass --tmp-location EPSG:4326 --exec g.extension m.analyse.trees url=grass-gis-addons/m.analyse.trees -s

# install an addon from mundialis
RUN grass --tmp-location EPSG:4326 --exec g.extension v.alkis.buildings.import url=https://github.com/mundialis/v.alkis.buildings.import -s

# install official addons
RUN grass --tmp-location EPSG:4326 --exec g.extension r.mapcalc.tiled
RUN grass --tmp-location EPSG:4326 --exec g.extension v.centerpoint
RUN grass --tmp-location EPSG:4326 --exec g.extension r.learn.ml2

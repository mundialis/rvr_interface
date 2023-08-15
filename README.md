# rvr_interface
Repo for code and script transfer between mundialis and RVR - GRASS GIS addons:

- **m.import.rvr** imports data for the processing of <b>gebaeudedetektion</b>,
<b>dachbegruenung</b> and/or <b>einzelbaumerkennung</b>.

- **r.import.dtm_nrw** downloads and imports the NRW digital terrain model
(DTM) 1m into the current mapset. Only the extent of the current region is
downloaded and imported with a 1m resolution.

- **r.import.ndsm_nrw** calculates an nDSM by subtracting input digital terrain
model (DTM) data (defined by the <b>dtm</b> parameter) from an input DSM
indicated by the <b>dsm</b> parameter. If no DTM is defined, NRW DTM data
is automatically imported using <a href="grass-gis-addons/r.import.dtm_nrw/r.import.dtm_nrw.html">r.import.dtm_nrw</a>.

- **r.in.pdal.worker** is a worker addon for <em>r.in.pdal</em> and is used in
<a href="grass-gis-addons/m.import.rvr/m.import.rvr.html">m.import.rvr</a>.


- **m.analyse.buildings**
  - **r.extract.buildings** extracts buildings as vectors and calculates height
   statistics (minimum, maximum, average, standard deviation, median,
     percentile) and presumable number of stories using an nDSM-raster,
     NDVI-raster, and FNK-vector (Flaechennutzungskatalog).
  - **r.extract.buildings.worker** is a worker module that is started by
<a href="grass-gis-addons/m.analyse.buildings/r.extract.buildings/r.extract.buildings.html">r.extract.buildings</a>.
  - **v.cd.areas** calculates differences between two vector layers
(e.g. classification and reference) by making use of v.overlay with operator
"xor". Only differences with a defined minimum size are extracted.
  - **v.cd.areas.worker** is a worker module that is started by
<a href="grass-gis-addons/m.analyse.buildings/v.cd.areas/v.cd.areas.html">v.cd.areas</a>.
  - **r.extract.greenroofs** extracts vegetated roofs from aerial photographs,
  an nDSM, a building vector layer and optionally an FNK
  (Flaechennutzungskatalog) and tree vector layer.
  - **r.extract.greenroofs.worker** is a worker module that is started by
<a href="grass-gis-addons/m.analyse.buildings/r.extract.greenroofs/r.extract.greenroofs.html">r.extract.greenroofs</a>.


- **m.analyse.trees**
  - **r.trees.peaks** assigns pixels to nearest peak (tree crown).
  - **r.trees.mltrain** generates training data for a machine learning (ML)
  model to detect trees and trains the model with these training data.
  - **r.trees.mlapply** applies the tree classification model
in parallel to the area of interest (current region).
  - **r.trees.mlapply.worker** applies classification model for a region
defined by a vector. This module should not be called directly, instead
it is called in parallel by <a href="grass-gis-addons/m.analyse.trees/r.trees.mlapply/r.trees.mlapply.html">r.trees.mlapply</a>.
  - **r.trees.postprocess** generates single tree delineations from tree pixels
   and geomorphological peaks.
  - **v.trees.param** calculates various tree parameters for tree crowns given
   as input vector map <b>treecrowns</b>.
  - **v.trees.param.worker** is used within <a href="grass-gis-addons/m.analyse.trees/v.trees.param/v.trees.param.html">v.trees.param</a> to calculate various tree parameters
   for tree crowns in parallel.
  - **v.trees.species** classifies trees in deciduous and coniferous trees.
  - **v.trees.cd** calculates the change between two given treecrown vector
  maps (<b>inp_t1</b> and <b>inp_t2</b> for time t1 and t2, respectively).
  - **v.trees.cd.worker** is a worker module that is started by
  <a href="grass-gis-addons/m.analyse.trees/v.trees.cd/v.trees.cd.html">v.trees.cd</a>.

## Building and running a docker image

In the folder with the Dockerfile, run
```bash
docker build -t rvr_interface:latest .
```

Instead of "latest", a version number can be used. This should create a local
docker image with all needed addons and dependencies. Once the docker image
has been created locally, it can be started with e.g.
```bash
docker run -it \
       -v /pfad/zu/grassdata:/grassdb \
       -v /pfad/zu/rvr_daten:/mnt/data \
       rvr_interface:latest sh
```

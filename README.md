# rvr_interface

Repo for code and script transfer between mundialis and RVR - GRASS GIS addons:

- **m.import.rvr** imports data for the processing of <b>buildings analysis</b>,
  <b>green roofs</b> and/or <b>trees analysis</b>.

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
  - **r.trees.traindata** generates training data for a machine learning (ML) model
    to detect trees and provides a preliminray tree candidate map in either vector or raster format.
  - **r.trees.mltrain** trains the ML model with the training data from before or own training data.
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
    maps (<b>input</b> and <b>reference</b> for time t1 and t2, respectively).
  - **v.trees.cd.worker** is a worker module that is started by
    <a href="grass-gis-addons/m.analyse.trees/v.trees.cd/v.trees.cd.html">v.trees.cd</a>.

## Building and running a docker image

In the folder with the Dockerfile, run

```bash
docker build -t rvr_interface:latest .
```

Instead of "latest", a version number can be used. This should create a local
docker image with all needed addons and dependencies. Once the docker image
has been created locally, it can be started on Linux with e.g.

```bash
xhost local:*
docker run -it --privileged --rm --ipc host \
       -v /path/to/grassdata:/grassdb \
       -v /path/to/rvr_daten:/mnt/data \
       -v "/tmp/.X11-unix:/tmp/.X11-unix:rw" \
       --env DISPLAY=$DISPLAY \
       --device="/dev/dri/card0:/dev/dri/card0" \
       rvr_interface:latest bash
```

On Windows you need to do the following before starting the docker container:

1. Install Docker Desktop
2. Download and install [VcXsrv Windows X Server](https://sourceforge.net/projects/vcxsrv/)
3. Start **Xlaunch** and configure it (see [here](https://dev.to/darksmile92/run-gui-app-in-linux-docker-container-on-windows-host-4kde)):
   - in the "Extra Settings" window enable "Disable access control"
   - in the "Finish Configuration" window click "Save configuration" and save it e.g. on the desktop

Now you can run the docker:

```bash
# get own IP adress (take the value of IPAdress e.g. 10.211.55.10 and not 127.0.0.1)
Get-NetIPAddress
# or
ipconfig

# set DISPLAY variable (set <YOUR-IP>)
set-variable -name DISPLAY -value <YOUR-IP>:0.0

# start Docker
docker run -it --privileged --rm --ipc host \
       -v C:/Users/path/to/grassdata:/grassdb \
       -v C:/Users/path/to/rvr_daten:/mnt/data \
       --env DISPLAY=$DISPLAY \
       --device="/dev/dri/card0:/dev/dri/card0" \
       rvr_interface:latest bash
```

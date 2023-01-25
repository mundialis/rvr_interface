# rvr_interface
Repo for Code and Script Transfer between mundialis and RVR - GRASS GIS addons:

- **r.extract.buildings** extracts buildings as vectors and calculates height statistics (minimum, maximum, average, standard deviation, median, percentile) and presumable number of stories using an nDSM-raster, NDVI-raster, and FNK-vector (Flaechennutzungskatalog).
- **r.import.dtm_nrw** downloads and imports the NRW digital terrain model (DTM) 1m into the current mapset. Only the extent of the current region is downloaded and imported with a 1m resolution.
- **r.import.ndsm_nrw** imports NRW digital terrain model (DTM) data using _r.import.dtm_nrw_ and calculates an nDSM combining the DTM data and the input DSM indicated by the _dsm_ parameter.
- **v.cd.buildings** calculates differences between two vector layers (e.g. classification and reference) by making use of v.overlay with operator "xor". Only differences with a defined minimum size are extracted.
- **r.extract.greenroofs** extracts vegetated roofs from aerial photographs, an nDSM, a building vector layer and optionally an FNK (Flaechennutzungskatalog) and tree vector layer.

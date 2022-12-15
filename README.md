# rvr_interface
Repo for Code and Script Transfer between mundialis and RVR - GRASS GIS addons:

- **r.extract.buildings** extracts buildings as vectors and calculates height statistics (minimum, maximum, average, standard deviation, median, percentile) and presumable number of stories using an nDOM-raster, NDVI-raster, and FNK-vector (Flaechennutzungskatalog).
- **r.import.dgm_nrw** downloads and imports the NRW DGM 1m into the current mapset. Only the extent of the current region is downloaded and imported with a 1m resolution.
- **r.import.ndom_nrw** imports NRW DGM data using _r.import.dgm_nrw_ and calculates an nDOM combining the DGM data and the input DOM indicated by the _dom_ parameter.
- **v.cd.buildings** calculates differences between two vector layers (e.g. classification and reference) by making use of v.overlay with operator "xor". Only differences with a defined minimum size are extracted.
- **r.extract.greenroofs** extracts vegetated roofs from aerial photographs, an nDOM, a building vector layer and optionally an FNK (Flaechennutzungskatalog) and tree vector layer.

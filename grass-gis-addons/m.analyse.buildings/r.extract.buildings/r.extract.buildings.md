## DESCRIPTION

*r.extract.buildings* extracts buildings as vectors and calculates
height statistics (minimum, maximum, average, standard deviation,
median, percentile) and presumable number of stories using an
nDSM-raster, NDVI-raster, and FNK-vector (Flaechennutzungskartierung).
As certain area codes from the FNK are used, the class codes have to be
consistent. The extraction can be based on an image segmentation using
[i.segment](i.segment.md), which requires the **-s** flag to be
activated. Note that this significantly extends the processing time.

A generic NDVI threshold is used to separate buildings from trees. The
NDVI threshold can be defined as a fixed NDVI value (on a scale from
0-255). Alternatively, the threshold can be defined by calculating the
n-th percentile (indicated by the **ndvi_perc** option) of NDVI values
from all vegetated areas. Vegetated areas are defined from the
FNK-vector - therefore the class codes have to be consistent. For this
alternative the parameter **used_thresh** must be set to **ndvi_perc**.

Only buildings with a defined minimum size and minimum height are
extracted. The average story height is assumed to be 3 meters.

The extraction works via tiles. Tile size has to be set by the
**tile_size** option. For serial processing use **nprocs=1**, for
parallel processing set number of cores to be used (e.g. **nprocs=8**).
The default uses available cores minus one. For processing the tiles the
addon uses the worker
[r.extract.buildings.worker](r.extract.buildings.worker.md).

## EXAMPLES

### Extraction using default values and the 5th percentile as NDVI threshold and a tile size of 2000m

```sh
r.extract.buildings ndsm=nDOM_Bottrop_2017_05m ndvi_raster=ndvi_Bottrop_2017 fnk_vector=FNK_Bottrop_2017 fnk_column=code_akt ndvi_perc=5 output=buildings_Bottrop_2017 memory=10000 tile_size=2000
```

### Extraction using a fixed NDVI threshold and a differing minimum size of buildings with a tile size of 2000m

```sh
r.extract.buildings ndsm=nDOM_Bottrop_2017_05m ndvi_raster=ndvi_Bottrop_2017 fnk_vector=FNK_Bottrop_2017 fnk_column=code_akt min_size=30 ndvi_thresh=145 output=buildings_Bottrop_2017 memory=10000 tile_size=2000
```

## SEE ALSO

*[r.mapcalc](https://grass.osgeo.org/grass-stable/manuals/r.mapcalc.html),
[i.segment](https://grass.osgeo.org/grass-stable/manuals/i.segment.html),
[r.quantile](https://grass.osgeo.org/grass-stable/manuals/r.quantile.html)*

## AUTHORS

Guido Riembauer, [mundialis GmbH & Co. KG](https://www.mundialis.de/)

Julia Haas, [mundialis GmbH & Co. KG](https://www.mundialis.de/)

## DESCRIPTION

*r.trees.traindata* generates a preliminary tree map for random forest
classification and/or post processing.

This module requires that pixels have been assigned to the nearest
potential tree peak with *r.trees.peaks*.

## EXAMPLES

### Generation of training data for tree and non-tree classification

```sh
r.trees.traindata green_raster=top.green \
                  blue_raster=top.blue \
                  nir_raster=top.nir \
                  ndvi_raster=top.ndvi \
                  ndwi_raster=top.ndwi \
                  ndgb_raster=top.ndgb \
                  ndsm=ndsm \
                  slope=ndsm_slope \
                  nearest=trees_nearest \
                  peaks=trees_peaks \
                  traindata_r=trees_raw_rast \
                  ndvi_threshold=130 \
                  nir_threshold=130 \
                  ndsm_threshold=1 \
                  slopep75_threshold=70 \
                  area_threshold=5 \
                  trees_pixel_ndvi=trees_pixel_ndvi
```

## SEE ALSO

*[m.analyse.trees](m.analyse.trees.md),
[r.geomorphon](https://grass.osgeo.org/grass-stable/manuals/r.geomorphon.html),*

## AUTHOR

Markus Metz, [mundialis](https://www.mundialis.de/), metz at
mundialis.de

Lina Krisztian, [mundialis](https://www.mundialis.de/), krisztian at
mundialis.de

Guido Riembauer, [mundialis](https://www.mundialis.de/), riembauer at
mundialis.de

Victoria-Leandra Brunn, [mundialis](https://www.mundialis.de/), brunn at
mundialis.de

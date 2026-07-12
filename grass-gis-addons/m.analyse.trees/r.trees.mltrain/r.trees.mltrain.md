## DESCRIPTION

*r.trees.mltrain* generates training data for a machine learning (ML)
model to detect trees and trains the model with these training data.

This model requires that pixels have been assigned to the nearest
potential tree peak with *r.trees.peaks*.

## EXAMPLES

### Generation of training data for tree and non-tree classification

```sh
r.trees.mltrain red_raster=top.red \
                green_raster=top.green \
                blue_raster=top.blue \
                nir_raster=top.nir \
                ndvi_raster=top.ndvi \
                ndwi_raster=top.ndwi \
                ndgb_raster=top.ndgb \
                ndsm=ndsm \
                slope=ndsm_slope \
                trees_pixel_ndvi=trees_pixel_ndvi \
                trees_raw_rast=trees_raw_rast \
                group=ml_input \
                save_model=ml_trees_randomforest.gz
```

## SEE ALSO

*[m.analyse.trees](m.analyse.trees.md),
[r.learn.train](r.learn.train.md),
[r.learn.predict](r.learn.predict.md)*

## AUTHOR

Markus Metz, [mundialis](https://www.mundialis.de/), metz at
mundialis.de

Lina Krisztian, [mundialis](https://www.mundialis.de/), krisztian at
mundialis.de

Guido Riembauer, [mundialis](https://www.mundialis.de/), riembauer at
mundialis.de

Victoria-Leandra Brunn, [mundialis](https://www.mundialis.de/), brunn at
mundialis.de

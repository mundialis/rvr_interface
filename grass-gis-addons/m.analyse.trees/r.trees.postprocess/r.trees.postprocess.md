## DESCRIPTION

*r.trees.postprocess* generates single tree delineations from tree
pixels and geomorphological peaks. The tree pixels are either the result
of a random forest (RF) model to detect trees, see *r.trees.mltrain* and
*r.trees.mlapply*. Or the output of a neural network (NN) model for tree
detection, see
[m.neural_network](https://github.com/mundialis/m.neural_network). Note,
that if the input is given by a NN approach, the *-n*-Flag must be
given. If the input is given by a RF approach no flag, but various
inputs (for further filtering) are needed.

## EXAMPLES

### Generation of single tree delineations from tree pixels generated with RF approach

```sh
r.trees.postprocess tree_pixels=mltrees \
                    nearest=trees_nearest \
                    peaks=trees_peaks \
                    red_raster=top.red \
                    green_raster=top.green \
                    blue_raster=top.blue \
                    nir_raster=top.nir \
                    ndvi_raster=top.ndvi \
                    ndwi_raster=top.ndwi \
                    ndgb_raster=top.ndgb \
                    ndsm=ndsm \
                    slope=ndsm_slope \
                    ndvi_threshold=130 \
                    nir_threshold=130 \
                    ndsm_threshold=1 \
                    slopep75_threshold=70 \
                    area_threshold=5 
```

### Generation of single tree delineations from tree pixels generated with NN approach

```sh
r.trees.postprocess tree_pixels=classification_patch \
                    nearest=trees_nearest \
                    peaks=trees_peaks \
                    area_threshold=5 \
                    -n
```

## SEE ALSO

*[r.geomorphon](https://grass.osgeo.org/grass-stable/manuals/r.geomorphon.html),
[r.learn.train](r.learn.train.md),
[r.learn.predict](r.learn.predict.md)*

## AUTHOR

Markus Metz, [mundialis](https://www.mundialis.de/), metz at
mundialis.de

Victoria-Leandra Brunn, [mundialis](https://www.mundialis.de/), brunn at
mundialis.de

Lina Krisztian, [mundialis](https://www.mundialis.de/), krisztian at
mundialis.de

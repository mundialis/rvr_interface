## DESCRIPTION

*r.trees.thresholds* proposes thresholds for NDVI and NIR as these
depend on the respective flight conditions.

## EXAMPLES

### Proposing thresholds for trainingdata generation and postprocessing

```sh
r.trees.thresholds forest=fnk forest_column=code2020 \
    nir_raster=top_nir_02 ndvi_raster=top_ndvi_02 \
    ndsm=ndsm ndsm_threshold=4
```

## SEE ALSO

*[m.analyse.trees](m.analyse.trees.md),
[r.quantile](https://grass.osgeo.org/grass-stable/manuals/r.geomorphon.html),*

## AUTHOR

Anika Weinmann, [mundialis](https://www.mundialis.de/), weinmann at
mundialis.de

Victoria-Leandra Brunn, [mundialis](https://www.mundialis.de/), brunn at
mundialis.de

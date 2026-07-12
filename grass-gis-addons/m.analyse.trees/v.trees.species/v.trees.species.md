## DESCRIPTION

*v.trees.species* classifies trees in deciduous and coniferous trees.

## EXAMPLES

### Classify trees in deciduous and coniferous trees

```sh
v.trees.species red_raster=top_red_02 green_raster=top_green_02 \
  blue_raster=top_blue_02 nir_raster=top_nir_02 ndvi_raster=top_ndvi_02 \
  ndsm=ndsm treecrowns=trees memory=10000
```

## SEE ALSO

*[r.mapcalc](https://grass.osgeo.org/grass-stable/manuals/r.mapcalc.html)*

## AUTHOR

Anika Weinmann, [mundialis GmbH & Co. KG](https://www.mundialis.de/)

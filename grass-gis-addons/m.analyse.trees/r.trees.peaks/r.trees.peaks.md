## DESCRIPTION

*r.trees.peaks* uses object heights from a normalized digital surface
model (nDSM) to detect peaks, to set unique IDs for these peaks and to
assign each pixel to the nearest peak using a cost analysis with
*r.cost* where inverted slope values are used as costs.

## EXAMPLES

### Tree peak extraction using default values

```sh
r.trees.peaks ndsm=ndsm_raster nearest=nearest_tree peaks=tree_peaks slope=ndsm_slope
```

## SEE ALSO

*[m.analyse.trees](m.analyse.trees.md),
[r.mapcalc](https://grass.osgeo.org/grass-stable/manuals/r.mapcalc.html),
[r.cost](https://grass.osgeo.org/grass-stable/manuals/r.cost.html),
[r.slope.aspect](https://grass.osgeo.org/grass-stable/manuals/r.slope.aspect.html)*

## AUTHOR

Markus Metz, [mundialis](https://www.mundialis.de/), metz at
mundialis.de

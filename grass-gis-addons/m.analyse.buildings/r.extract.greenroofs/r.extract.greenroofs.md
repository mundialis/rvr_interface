## DESCRIPTION

*r.extract.greenroofs* extracts vegetated roofs from aerial photographs,
an nDSM, a building vector layer and optionally an FNK
(Flaechennutzungskartierung) and tree vector layer. The module generates
two outputs: The buildings outlines that have vegetated roofs
(*output_buildings*) with an added attribute column containing the
percentage of vegetated roof area with respect to total roof area. The
second output (*output_vegetation*) contains only the vegetation
objects.

The module works best when a tree vector layer is used as input via the
*trees* parameter. If this is not given, *r.extract.greenroofs* tries to
eliminate false alarms by overhanging trees via the nDSM difference to
the remaining roof area.

Internally, a normalized difference green-blue ratio is used to
discriminate vegetated from non-vegetated areas (the NDVI is not
sensitive enough for sparse roof vegetation). A threshold for the
green-blue ratio can be defined by the *gb_thresh* parameter. Empirical
testing showed good results for a value of around *gb_thresh=145* (on a
scale from 0 to 255). The threshold can also be automatically estimated
from green areas defined in the FNK. For this, the parameter
**used_thresh** must be set to **gb_perc** and the *fnk*, *fnk_column*,
and *gb_perc* parameters must be given. The latter defines the
percentile of pixels in vegetated areas to define as gleen-blue ratio
threshold. Empirical testing yielded good results for *gb_perc=25* (=1st
quartile).

Optionally, the analysis can be run object-based instead of pixel-based
by using the *-s* flag. This typically improves the result, but takes up
more processing time. If no appropriate *gb_thresh* value is known, it
is recommended to run the module a few times without the *-s* flag and
inspect the result to identify a proper threshold. The final run should
then be performed with the *-s* flag.

The *min_veg_size* and *min_veg_proportion* parameters can be used to
eliminate vegetated roof areas by size or proportion of total roof area.

## EXAMPLES

### Extract green roofs by a fixed threshold of 145, use object based detection

```sh
r.extract.greenroofs ndsm=ndsm_raster ndvi=ndvi_raster red=dop_red green=dop_green blue=dop_blue gb_thresh=145 buildings=buildings_vector trees=trees_vector output_buildings=result_buildings output_vegetation=result_vegetation -s
```

### Extract green roofs by an estimated threshold from the FNK using the 25% percentile as threshold, use pixel based detection

```sh
r.extract.greenroofs ndsm=ndsm_raster ndvi=ndvi_raster red=dop_red green=dop_green blue=dop_blue gb_perc=25 fnk=fnk_vector fnk_column=fnk_code buildings=buildings_vector trees=trees_vector output_buildings=result_buildings output_vegetation=result_vegetation
```

## SEE ALSO

*[r.mapcalc](https://grass.osgeo.org/grass-stable/manuals/r.mapcalc.html),
[i.segment](https://grass.osgeo.org/grass-stable/manuals/i.segment.html),
[r.quantile](https://grass.osgeo.org/grass-stable/manuals/r.quantile.html)*

## AUTHORS

Julia Haas, [mundialis GmbH & Co. KG](https://www.mundialis.de/)

Guido Riembauer, [mundialis GmbH & Co. KG](https://www.mundialis.de/)

Anika Weinmann, [mundialis GmbH & Co. KG](https://www.mundialis.de/)

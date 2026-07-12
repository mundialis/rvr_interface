## DESCRIPTION

*r.import.ndsm_nrw* calculates an nDSM by subtracting input digital
terrain model (DTM) data (defined by the **dtm** parameter) from an
input DSM indicated by the **dsm** parameter. If no DTM is defined, NRW
DTM data is automatically imported using
[r.import.dtm_nrw](r.import.dtm_nrw.md). Potential NoData areas in the
**dsm** are filled beforehand by *r.fillnulls.html* and both rasters are
resampled to a common grid. The final nDSM is resampled to match the
extent and resolution of the current computational region.

## EXAMPLE

```sh
r.import.ndsm_nrw dsm=laz_import_dsm output_ndsm=ndsm memory=8000
```

## SEE ALSO

*[r.import.dtm_nrw](r.import.dtm_nrw.md),
[r.fillnulls](https://grass.osgeo.org/grass-stable/manuals/r.fillnulls.html),
[r.mapcalc](https://grass.osgeo.org/grass-stable/manuals/r.mapcalc.html)*

## AUTHORS

Guido Riembauer, [mundialis GmbH & Co. KG](https://www.mundialis.de/)

Anika Weinmann, [mundialis GmbH & Co. KG](https://www.mundialis.de/)

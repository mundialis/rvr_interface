## DESCRIPTION

*r.import.dtm_nrw* downloads and imports the NRW digital terrain model
(DTM) 1m into the current mapset. Only the extent of the current region
is downloaded and imported with a 1m resolution. Note that data is only
available for NRW and will be imported on a best-effort basis: If the
current region exceeds NRW, all available DTM data for the region is
still imported, but GRASS will give a warning.

## EXAMPLE

```sh
r.import.dtm output=dtm_1m
```

## SEE ALSO

*[r.in.xyz](https://grass.osgeo.org/grass-stable/manuals/r.in.xyz.html)*

## REFERENCES

- [download
  source](https://www.opengeodata.nrw.de/produkte/geobasis/hm/dtm1_xyz/dtm1_xyz/)
- [metadata](https://www.bezreg-koeln.nrw.de/brk_internet/geobasis/hoehenmodelle/digitale_gelaendemodelle/gelaendemodell/index.html)

## AUTHORS

Guido Riembauer, [mundialis GmbH & Co. KG](https://www.mundialis.de/)

Anika Weinmann, [mundialis GmbH & Co. KG](https://www.mundialis.de/)

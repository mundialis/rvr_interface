[![image-alt](grass_logo.png)](https://grass.osgeo.org/grass-stable/manuals/index.html)

------------------------------------------------------------------------

## NAME

***m.analyse.buildings*** - GRASS GIS addons for detection and
comparison of buildings and detection of vegetated roofs on buildings.

## KEYWORDS

[raster](https://grass.osgeo.org/grass-stable/manuals/raster.html),
[vector](https://grass.osgeo.org/grass-stable/manuals/vector.html)

## DESCRIPTION

The *m.analyse.buildings* toolset consists of several modules.

- [r.extract.buildings](r.extract.buildings.md): Extracts buildings from
  nDSM, NDVI and FNK
- [r.extract.greenroofs](r.extract.greenroofs.md): Extracts green roofs
  from nDSM, NDVI, GB-Ratio, FNK and building outlines
- [v.cd.areas](v.cd.areas.md): Calculates difference between two vector
  layers (buildings)

## REQUIREMENTS

The following Python libraries are needed.

- psutil
- pyproj
- requests
- tqdm

## AUTHORS

Julia Haas, [mundialis](https://www.mundialis.de/)

Guido Riembauer, [mundialis](https://www.mundialis.de/)

Anika Weinmann, [mundialis](https://www.mundialis.de/)

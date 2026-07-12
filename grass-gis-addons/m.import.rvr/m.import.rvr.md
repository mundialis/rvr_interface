## DESCRIPTION

*m.import.rvr* imports data for the processing of **buildings
analysis**, **green roofs**, **trees analysis** and/or \>**neural
network**. The module takes as options the paths to the input
directories and files. With the flag **-c** the module checks only if
all required input options for the selected processing **type** are set.
The module imports the following data for the different processing
**type**s:

- **buildings analysis**
  - Flächennutzungskartierung (FNK): imported from given vector file
    **fnk_file**
  - Reference buildings: imported from given vector file
    **reference_buildings_file** or from openNRW if **-b** is set
  - Digital orthophotos (DOP): GTIFF files from given directory
    **dop_dir** imported and resampled to 0.5 m
  - Digital surface model (DSM): LAZ files from given directory
    **dsm_dir** imported and resampled to 0.5 m
  - Digital terrain model (DTM): from given raster file **dtm_file**, or
    tiles from a directory with XYZ files, or if not set from openNRW
    imported and resampled to 0.5 m
  - Normalized Difference Vegetation Index (NDVI): calculated on the
    basis of **DOP**
  - Normalized Digital Surface Model (nDSM): calculated on the basis of
    **DSM** and **DTM**
- **green roofs**
  - Flächennutzungskartierung (FNK): imported from given vector file
    **fnk_file**
  - Reference Trees: imported from given vector file **tree_file**
  - Reference buildings: imported from given vector file
    **houserings_file** or from openNRW if **-b** is set
  - Digital orthophotos (DOP): GTIFF files from given directory
    **dop_dir** imported and resampled to 0.5 m
  - Digital surface model (DSM): LAZ files from given directory
    **dsm_dir** imported and resampled to 0.5 m
  - Digital terrain model (DTM): from given raster file **dtm_file**, or
    tiles from a directory with XYZ files, or if not set from openNRW
    imported and resampled to 0.5 m
  - Normalized Difference Vegetation Index (NDVI): calculated on the
    basis of **DOP** and scaled to 0 to 255
  - Normalized Digital Surface Model (nDSM): calculated on the basis of
    **DSM** and **DTM**
- **trees analysis**
  - True digital orthophotos (TOP): GTIFF files from given directory
    **top_dir** imported and resampled to 0.2 m
  - Reference buildings: imported from given vector file
    **reference_buildings_file** or from openNRW if **-b** is set
  - Digital surface model (DSM): LAZ files from given directory
    **dsm_dir** imported and resampled to 0.2 m
  - Digital terrain model (DTM): from given raster file **dtm_file**, or
    tiles from a directory with XYZ files, or if not set from openNRW
    imported and resampled to 0.2 m
  - Normalized Difference Vegetation Index (NDVI): calculated on the
    basis of **TOP** and scaled to 0 to 255
  - Normalized Digital Surface Model (nDSM): calculated on the basis of
    **DSM** and **DTM**
- **neural network**
  - True digital orthophotos (TOP): GTIFF files from given directory
    **top_dir** imported and resampled to 0.2 m
  - Digital surface model (DSM): LAZ files from given directory
    **dsm_dir** imported and resampled to 0.2 m
  - Digital terrain model (DTM): from given raster file **dtm_file**, or
    tiles from a directory with XYZ files, or if not set from openNRW
    imported and resampled to 0.2 m
  - Normalized Digital Surface Model (nDSM): calculated on the basis of
    **DSM** and **DTM**

## REQUIREMENTS

The module needs other GRASS GIS addons for the different data imports.
For example the following addons and python libraries have to be
installed:

```sh
pip3 install py7zr pyproj tqdm requests
g.extension v.alkis.buildings.import url=https://github.com/mundialis/v.alkis.buildings.import
g.extension r.import.dtm_nrw url=/path/to/grass-gis-addons/r.import.dtm_nrw
g.extension r.import.ndsm_nrw url=/path/to/grass-gis-addons/r.import.ndsm_nrw
g.extension r.in.pdal.worker url=/path/to/grass-gis-addons/r.in.pdal.worker
g.extension r.dem.import url=https://github.com/mundialis/r.dem.import
```

## EXAMPLES

### Import data for buildings analysis for Dinslaken 2020

In this example the DTM data will be downloaded from
[OpenNRW](https://www.bezreg-koeln.nrw.de/brk_internet/geobasis/) and
also the reference data for buildings will be downloaded from
[OpenNRW](https://www.bezreg-koeln.nrw.de/brk_internet/geobasis/).

```sh
  DATAFOLDER=/mnt/data/Originaldaten_RVR/Dinslaken
  m.import.rvr memory=6000 type='buildings analysis' \
    area=/mnt/data/Dinslaken/fnk_dinslaken/fnk_dinslaken.shp \
    fnk_file=/mnt/data/Dinslaken/fnk_dinslaken/fnk_dinslaken.shp \
    fnk_column=code_2020 \
    dsm_dir=${DATAFOLDER}/2020_Sommer/Punktwolke_2_5D_RGBI \
    dop_dir=${DATAFOLDER}/2020_Sommer/DOP -b
```

### Import data for green roofs detection for Dinslaken 2020

```sh
DATAFOLDER=/mnt/data/Originaldaten_RVR/Dinslaken
m.import.rvr memory=6000 type='green roofs' -b \
  area=/mnt/data/Dinslaken/fnk_dinslaken/fnk_dinslaken.shp \
  fnk_file=/mnt/data/Dinslaken/fnk_dinslaken/fnk_dinslaken.shp \
  fnk_column=code_2020 \
  dsm_dir=${DATAFOLDER}/2020_Sommer/Punktwolke_2_5D_RGBI \
  dop_dir=${DATAFOLDER}/2020_Sommer/DOP -b
```

### Import data for trees analysis for Herne 2020

```sh
DATAFOLDER=/mnt/projects/rv_ruhr_baumstandorte/geodata/rvr_data_Herne_2020/
m.import.rvr memory=6000 type='trees analysis' -b \
  area=${DATAFOLDER}/test_area.gpkg \
  reference_buildings_file=${DATAFOLDER}/Shapes/herne_hausumringe_100m_puffer.shp \
  top_dir=${DATAFOLDER}/TOP/ \
  top_tindex=${DATAFOLDER}/top_tindex.gpkg \
  dsm_dir=${DATAFOLDER}/Punktwolke_2_5D_RGBI/ \
  dsm_tindex=${DATAFOLDER}/dsm_tindex.gpkg \
  dtm_file=${DATAFOLDER}/DGM/2020_Herne_DGM10_100m_Puffer.tif
```

### Import data for neural network label traindata for Sonsbeck 2020

```sh
CITY=Sonsbeck
YEAR=2020
BEFLIEGUNG="08-05"
DATA_DIR="/media/mundialis_daten/projekte/rvr_grassgis-addon-wartung/Testdaten"
CITY_DIR="${DATA_DIR}/${CITY}"
m.import.rvr type="neural network" \
  area=/media/mundialis_daten/projekte/rvr_grassgis-addon-wartung/Testdaten/Sonsbeck/study_area_4x4km_Sonsbeck.gpkg \
  dtm_file="${CITY_DIR}/${YEAR}/${BEFLIEGUNG}/DGM1/TIFF_corrected/MOSAIC/DGM1_${CITY}_${YEAR}_corrected.tif" \
  dsm_dir="${CITY_DIR}/${YEAR}/${BEFLIEGUNG}/2_5D" \
  top_dir="${CITY_DIR}/${YEAR}/${BEFLIEGUNG}/TOP"
```

## SEE ALSO

*[r.import](https://grass.osgeo.org/grass-stable/manuals/r.import.html),
[r.in.pdal](https://grass.osgeo.org/grass-stable/manuals/r.in.pdal.html),
[v.alkis.buildings.import](v.alkis.buildings.import.md),
[r.import.ndsm_nrw](r.import.ndsm_nrw.md),
[r.import.dtm_nrw](r.import.dtm_nrw.md),
[r.dem.import](r.dem.import.md)*

## AUTHORS

Anika Weinmann, [mundialis GmbH & Co. KG](https://www.mundialis.de/)  
Momen Mawad, [mundialis GmbH & Co. KG](https://www.mundialis.de/)  
Victoria-Leandra Brunn, [mundialis GmbH & Co.
KG](https://www.mundialis.de/)

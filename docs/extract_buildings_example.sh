#!/bin/bash
# This script shows how the building and greenroof detection could be done
# with a shell script according to the documentation with default values.
# Author:  RVR
# Date:    06.10.2023
# Version: 1.0.0

# Create a new mapset for the analysis
g.mapset -c example_mapset

# Declare a variable for the data folder
DATAFOLDER=/mnt/data

# Start import process for building detection
# Change file names and paths accordingly
m.import.rvr type=gebaeudedetektion \
area=${DATAFOLDER}/AOI/AOI.gpkg \
fnk_file=${DATAFOLDER}/FNK/FNK.gpkg fnk_column=codeXY \
reference_buildings_file=${DATAFOLDER}/ALKIS/ALKIS.gpkg \
dop_dir=${DATAFOLDER}/DOP/ \
dop_tindex=${DATAFOLDER}/dop_tindex.gpkg \
dsm_dir=${DATAFOLDER}/2_5D/ \
dsm_tindex=${DATAFOLDER}/dsm_tindex.gpkg \
dtm_file=${DATAFOLDER}/DGM1/DGM1_corrected.tif \
memory=300 \
nprocs=-2

# Set region
g.region rast=dop_red_05 -p

# Start building detection with ndvi_thresh
r.extract.buildings \
ndsm=ndsm \
ndvi_raster=dop_ndvi_05 \
fnk_vector=fnk fnk_column=codeXY \
ndvi_thresh=145 \
output=buildings \
memory=300 \
nprocs=-2 \
tile_size=1000

# Set region
g.region rast=dop_red_05 -p

# Start change detection with quality measures
v.cd.areas -q \
input=buildings \
reference=reference_buildings \
min_size=5 \
max_fd=2.5 \
output=buildings_alkis_difference \
nprocs=-2 \
tile_size=1000

# Export building results
v.out.ogr input=buildings output=/results/buildings.gpkg format=GPKG
v.out.ogr input=buildings_alkis_difference output=/results/buildings_alkis_difference.gpkg format=GPKG

# Import trees for greenroof detection
# Already imported data will be skipped
m.import.rvr type=dachbegruenung \
area=${DATAFOLDER}/AOI/E_Bredeney_gmk_nrw.gpkg \
building_outlines_file=/results/buildings.gpkg \
tree_file=${DATAFOLDER}/trees.gpkg \
dop_dir=${DATAFOLDER}/DOP/ \
dop_tindex=${DATAFOLDER}/dop_tindex.gpkg \
dsm_dir=${DATAFOLDER}/2_5D/ \
dsm_tindex=${DATAFOLDER}/dsm_tindex.gpkg \
dtm_file=${DATAFOLDER}/DGM1/DGM1_corrected.tif \
memory=300 \
nprocs=-2

# Set region
g.region rast=dop_red_05 -p

# Start import process for greenroof detection
# with detected buildings, gb_thresh and
# segmentation
r.extract.greenroofs -s \
ndsm=ndsm \
ndvi=dop_ndvi_05 \
red=dop_red_05 green=dop_green_05 blue=dop_blue_05 \
buildings=building_outlines \
trees=trees \
gb_thresh=145 \
min_veg_size=5 \
min_veg_proportion=10 \
output_buildings=begruente_gebaeude \
output_vegetation=dachgruen \
memory=300 \
nprocs=-2 \
tile_size=1000

# Export greeenroof results
v.out.ogr input=begruente_gebaeude output=/results/begruente_gebaeude.gpkg format=GPKG
v.out.ogr input=dachgruen output=/results/dachgruen.gpkg format=GPKG

# Export raster data
r.out.gdal input=dop_ndvi_05 output=/results/ndvi_05.tif format=GTiff createopt="COMPRESS=DEFLATE"
r.out.gdal input=ndsm output=/results/ndsm_05.tif format=GTiff createopt="COMPRESS=DEFLATE"
r.out.gdal input=dsm_05 output=/results/dsm_05.tif format=GTiff createopt="COMPRESS=DEFLATE"
r.out.gdal input=dtm_05 output=/results/dtm_05.tif format=GTiff createopt="COMPRESS=DEFLATE"
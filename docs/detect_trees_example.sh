#!/bin/bash
# This script shows how the tree detection could be done
# with a shell script according to the documentation with default values.
# Author:  RVR
# Date:    24.10.2023
# Version: 1.0.0

# Create a new mapset for the analysis
g.mapset -c example_mapset

# Declare a variable for the data folder
DATAFOLDER=/mnt/data

# Start import process for tree detection
# Change file names and paths accordingly
m.import.rvr type=einzelbaumerkennung \
area=${DATAFOLDER}/AOI/AOI.gpkg \
top_dir=${DATAFOLDER}/TOP/ \
top_tindex=${DATAFOLDER}/top_tindex.gpkg \
dsm_dir=${DATAFOLDER}/2_5D/ \
dsm_tindex=${DATAFOLDER}/dsm_tindex.gpkg \
dtm_file=${DATAFOLDER}/DGM1/DGM1_corrected.tif \
reference_buildings_file=${DATAFOLDER}/ALKIS/ALKIS.gpkg \
memory=300 \
nprocs=-2

# Set region
g.region rast=ndsm

# Start tree detection by calculating tree peaks first
r.trees.peaks \
ndsm=ndsm \
forms_res=0.8 \
nearest=nearest_tree \
peaks=tree_peaks \
slope=ndsm_slope \
tile_size=2000 \
memory=300

# Set region
g.region rast=ndsm

# Create training data and train random forest modell
r.trees.mltrain \
red_raster=top_red_02 green_raster=top_green_02 blue_raster=top_blue_02 nir_raster=top_nir_02 ndvi_raster=top_ndvi_02 ndsm=ndsm slope=ndsm_slope nearest=nearest_tree peaks=tree_peaks \
ndvi_threshold=130 \
nir_threshold=130 \
ndsm_threshold=1 \
slopep75_threshold=70 \
area_threshold=5 \
group=ml_input \
save_model=ml_trees_randomforest_AOI_year.gz \
memory=300

# Set region
g.region rast=ndsm

# Apply random forest model to area of interest
r.trees.mlapply \
area=study_area \
group=ml_input \
model=ml_trees_randomforest_AOI_year.gz \
output=tree_pixels \
tile_size=1000 \
nprocs=-2

# Set region
g.region rast=ndsm

# Grouping classified pixels in postprocessing step
r.trees.postprocess \
tree_pixels=tree_pixels \
green_raster=top_green_02 blue_raster=top_blue_02 \
nir_raster=top_nir_02 \
ndvi_raster=top_ndvi_02 \
ndsm=ndsm \
slope=ndsm_slope \
nearest=nearest_tree \
peaks=tree_peaks \
ndvi_threshold=130 \
nir_threshold=130 \
ndsm_threshold=1 \
slopep75_threshold=70 \
area_threshold=5 \
trees_raster=tree_objects \
trees_vector=tree_objects \
memory=300

# Set region
g.region rast=ndsm

# Calculating tree parameters
v.trees.param \
treecrowns=tree_objects \
ndom=ndsm \
ndvi=top_ndvi_02 \
buildings=reference_buildings \
distance_tree=500 \
treeparamset=position,hoehe,dm,volumen,flaeche,ndvi,dist_geb,dist_baum \
memory=300 \
nprocs=-2

# Set region
g.region rast=ndsm

# Detecting deciduous and coniferous trees
v.trees.species \
treecrowns=tree_objects \
red_raster=top_red_02 green_raster=top_green_02 blue_raster=top_blue_02 \
nir_raster=top_nir_02 \
ndvi=top_ndvi_02 \
ndsm=ndsm \
memory=300

# Export tree results
v.out.ogr input=tree_objects output=/results/treecrowns_year.gpkg format=GPKG

# Export raster data
r.out.gdal input=ndsm output=/results/ndsm_year.tif format=GTiff createopt="BIGTIFF=YES"
r.out.gdal input=top_ndvi_02 output=/results/ndvi_year.tif format=GTiff createopt="BIGTIFF=YES"
r.out.gdal input=ndgb output=/results/ndgb_year.tif format=GTiff createopt="BIGTIFF=YES"
r.out.gdal input=ndwi output=/results/ndwi_year.tif format=GTiff createopt="BIGTIFF=YES"
r.out.gdal input=nearest_tree output=/results/nearest_tree_year.tif format=GTiff createopt="BIGTIFF=YES"
r.out.gdal input=tree_peaks output=/results/tree_peaks_year.tif format=GTiff createopt="BIGTIFF=YES"
r.out.gdal input=ndsm_slope output=/results/ndsm_slope_year.tif format=GTiff createopt="BIGTIFF=YES"
r.out.gdal input=tree_objects output=/results/tree_objects_year.tif format=GTiff createopt="BIGTIFF=YES"
r.out.gdal input=tree_pixels output=/results/tree_pixels_year.tif format=GTiff createopt="BIGTIFF=YES"

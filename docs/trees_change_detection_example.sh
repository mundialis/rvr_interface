#!/bin/bash
# This script shows how the tree change detection could be done
# with a shell script according to the documentation with default values.
# Author:  RVR
# Date:    25.10.2023
# Version: 1.0.0

# Create a new mapset for the analysis
g.mapset -c example_mapset

# Declare a variable for the data folder
DATAFOLDER=/mnt/data

# Import two tree vector layers for change detection
# Change file names and paths accordingly
v.in.ogr input=${DATAFOLDER}/Trees/trees_AOI_year1.gpkg output=trees_year1
v.in.ogr input=${DATAFOLDER}/Trees/trees_AOI_year2.gpkg output=trees_year2

# Start change detection
v.trees.cd \
inp_t1=trees_year1 inp_t2=trees_year2 \
vec_congr_thr=90 \
vec_diff_min_size=0.25 \
vec_diff_max_fd=2.5 \
output=cd_year1_year2 \
tile_size=1000 \
nprocs=-2

# Export tree change detection results
v.out.ogr input=cd_year1_year2_congruent output=/results/cd_year1_year2_congruent.gpkg format=GPKG
v.out.ogr input=cd_year1_year2_only_trees_year1 output=/results/cd_year1_year2_only_trees_year1.gpkg format=GPKG
v.out.ogr input=cd_year1_year2_only_trees_year2 output=/results/cd_year1_year2_only_trees_year2.gpkg format=GPKG
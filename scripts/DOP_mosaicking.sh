#!/bin/sh
#
########################################################################
#
# MODULE:    DOP Mosaicking
# AUTHOR(S): Julia Haas, Guido Riembauer and mundialis GmbH & Co. KG
# PURPOSE:   Script to mosaick DOP files with GDAL
# COPYRIGHT: (c) 2021 by Julia Haas, Guido Riembauer and mundialis GmbH & Co. KG
#
#   This program is free software under the GNU General Public
#   License (>=v2). Read the file COPYING that comes with GRASS
#   for details.
#
########################################################################

# SRS is EPSG:25832 (ETRS89 / UTM zone 32N)

# Variables
TILE_LIST=$1
OUTPUT=$2
VRT=${OUTPUT%.tif}.vrt
TMP=${OUTPUT%.tif}_tmp.tif


### nothing to change below ###

# Build mosaic as vrt and define CRS
gdalbuildvrt -a_srs EPSG:25832 -input_file_list ${TILE_LIST} ${VRT}

# Resample and convert to tif
gdalwarp -of GTIFF -co COMPRESS=DEFLATE -tr 0.5 0.5 -tap -r med ${VRT} ${TMP}

# Enforce correct projection
gdal_translate -of GTIFF -co COMPRESS=DEFLATE -a_srs EPSG:25832 ${TMP} ${OUTPUT}

# remove intermediate result
rm -f ${TMP}

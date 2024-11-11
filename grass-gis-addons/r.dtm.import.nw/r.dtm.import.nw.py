#!/usr/bin/env python3
#
############################################################################
#
# MODULE:      r.dtm.import.nw
# AUTHOR(S):   Victoria-Leandra Brunn
#
# PURPOSE:     Downloads DTM for Nordrhein-Westfalen and aoi
# COPYRIGHT:   (C) 2024 by mundialis GmbH & Co. KG and the GRASS
#              Development Team
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
############################################################################

# %module
# % description: Downloads DTM for Nordrhein-Westfalen and aoi.
# % keyword: raster
# % keyword: import
# % keyword: DTM
# % keyword: DGM
# % keyword: open-geodata-germany
# %end

# %option G_OPT_V_INPUT
# % key: aoi
# % description: Polygon of the area of interest to set region
# % required: no
# %end

# %option
# % key: download_dir
# % label: Path to output folder
# % description: Path to download folder
# % required: no
# % multiple: no
# %end

# %option G_OPT_R_OUTPUT
# % description: Name for output raster map
# %end

# %flag
# % key: k
# % label: Keep downloaded data in the download directory
# %end

# %flag
# % key: r
# % label: Use native data resolution
# %end

# %rules
# % requires_all: -k,download_dir
# %end

import atexit
import os
import grass.script as grass

from grass_gis_helpers.cleanup import general_cleanup
from grass_gis_helpers.data_import import (
    download_and_import_tindex,
    get_list_of_tindex_locations,
)
from grass_gis_helpers.open_geodata_germany.download_data import (
    check_download_dir,
)
from grass_gis_helpers.raster import adjust_raster_resolution, create_vrt

# set constant variables
TINDEX = (
    "https://github.com/vbrunn/tile-indices/raw/NW_DTM_tileidx/DTM/NW/"
    "nw_dtm_tindex_proj.gpkg.gz"
)
DATA_BASE_URL = (
    "https://www.opengeodata.nrw.de/produkte/geobasis/hm/dgm1_tiff/"
    "dgm1_tiff/"
)

ID = grass.tempname(12)
ORIG_REGION = f"original_region_{ID}"

# set global variables
keep_data = False
download_dir = None
rm_rasters = []
rm_vectors = []


def cleanup():
    """Cleaning up function"""
    rm_dirs = []
    if not keep_data:
        if download_dir:
            rm_dirs.append(download_dir)
    general_cleanup(
        orig_region=ORIG_REGION,
        rm_rasters=rm_rasters,
        rm_vectors=rm_vectors,
        rm_dirs=rm_dirs,
    )


def main():
    """Main function of r.dtm.import.nw"""
    global rm_rasters, rm_vectors, keep_data, download_dir

    aoi = options["aoi"]
    download_dir = check_download_dir(options["download_dir"])
    output = options["output"]
    keep_data = flags["k"]
    native_res = flags["r"]

    # save original region
    grass.run_command("g.region", save=ORIG_REGION, quiet=True)
    ns_res = grass.region()["nsres"]

    # set region if aoi is given
    if aoi:
        grass.run_command("g.region", vector=aoi, flags="a")

    # get tile index
    tindex_vect = f"dtm_tindex_{ID}"
    rm_vectors.append(tindex_vect)
    download_and_import_tindex(TINDEX, tindex_vect, download_dir)

    # get download urls which overlap with aoi
    url_tiles = get_list_of_tindex_locations(tindex_vect, aoi)

    # import DTM directly
    grass.message(_("Importing DTM..."))
    all_dtm = []
    for url in url_tiles:
        dtm_name = os.path.splitext(os.path.basename(url))[0].replace("-", "")
        if "/vsicurl/" not in url:
            url = f"/vsicurl/{url}"
        grass.run_command(
            "r.import",
            input=url,
            output=dtm_name,
            extent="region",
            overwrite=True,
            quiet=True,
        )
        all_dtm.append(dtm_name)

    # resample / interpolate whole VRT (because interpolating single files leads
    # to empty rows and columns)
    # check resolution and resample / interpolate data if needed
    if not native_res:
        # create VRT
        vrt = f"vrt_dtm_{ID}"
        rm_rasters.append(vrt)
        create_vrt(all_dtm, vrt)

        grass.message(_("Resampling / interpolating data..."))
        grass.run_command("g.region", raster=vrt, res=ns_res, flags="a")
        adjust_raster_resolution(vrt, output, ns_res)
        rm_rasters.extend(all_dtm)
    else:
        # create VRT
        create_vrt(all_dtm, output)

    grass.message(_(f"DTM raster map <{output}> is created."))


if __name__ == "__main__":
    options, flags = grass.parser()
    atexit.register(cleanup)
    main()

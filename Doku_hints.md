## Dokumentations Gedankenstützen

Änderungen nach r.trees.peaks
* Möglichkeit 1: Raster und direkt in r.trees.postprocess:
r.trees.traindata green_raster=dop_green blue_raster=dop_blue nir_raster=dop_nir ndvi_raster=ndvi_raster ndsm=ndsm slope=slope2 nearest=nearest_tree2 peaks=tree_peaks2 traindata_r=traindata_raster1 trees_pixel_ndvi=trees_pixel_ndvi1 --overwrite
r.trees.postprocess tree_pixels=traindata_raster1 green_raster=dop_green blue_raster=dop_blue nir_raster=dop_nir ndvi_raster=ndvi_raster ndsm=ndsm slope=slope2 nearest=nearest_tree2 peaks=tree_peaks2 trees_raster=tree_objects3 trees_vector=tree_objects3 --overwrite

* Möglichkeit 2: Raster und ML (r.trees.mltrain, r.trees.mlapply, r.trees.postprocess)
r.trees.traindata green_raster=dop_green blue_raster=dop_blue nir_raster=dop_nir ndvi_raster=ndvi_raster ndsm=ndsm slope=slope2 nearest=>
r.trees.mltrain red_raster=dop_red green_raster=dop_green blue_raster=dop_blue nir_raster=dop_nir ndvi_raster=ndvi_raster ndsm=ndsm slope=slope trees_pixel_ndvi=trees_pixel_ndvi1 trees_raw_r=traindata_raster1 num_samples=8000 group=ml_input_test save_model=test_ml_trees_randomforest.gz --o
r.trees.mlapply area=aoi group=ml_input_test model=test_ml_trees_randomforest.gz output=tree_pixels4 --overwrite
r.trees.postprocess tree_pixels=tree_pixels4 green_raster=dop_green blue_raster=dop_blue nir_raster=dop_nir ndvi_raster=ndvi_raster ndsm=ndsm slope=slope2 nearest=nearest_tree2 peaks=tree_peaks2 trees_raster=tree_objects4 trees_vector=tree_objects4 --overwrite


* Möglichkeit 3: Vektor und ML (r.trees.mltrain, r.trees.mlapply, r.trees.postprocess)
r.trees.traindata green_raster=dop_green blue_raster=dop_blue nir_raster=dop_nir ndvi_raster=ndvi_raster ndsm=ndsm slope=slope2 nearest=nearest_tree2 peaks=tree_peaks2 traindata_v=traindata_vector1 trees_pixel_ndvi=trees_pixel_ndvi2 --overwrite
r.trees.mltrain red_raster=dop_red green_raster=dop_green blue_raster=dop_blue nir_raster=dop_nir ndvi_raster=ndvi_raster ndsm=ndsm slope=slope trees_pixel_ndvi=trees_pixel_ndvi1 trees_raw_v=traindata_vector1 num_samples=4000 group=ml_input_test save_model=test_ml_trees_randomforest.gz --o
r.trees.mlapply area=aoi group=ml_input_test model=test_ml_trees_randomforest.gz output=tree_pixels5 --overwrite
r.trees.postprocess tree_pixels=tree_pixels4 green_raster=dop_green blue_raster=dop_blue nir_raster=dop_nir ndvi_raster=ndvi_raster ndsm=ndsm slope=slope2 nearest=nearest_tree2 peaks=tree_peaks2 trees_raster=tree_objects5 trees_vector=tree_objects5 --overwrite

* NICHT möglich: Vektor direkt in r.trees.postprocess
Es fehlt eine kleine Abfrage zur Rasterisierung. Wäre simpel hinzuzufügen, falls notwendig.


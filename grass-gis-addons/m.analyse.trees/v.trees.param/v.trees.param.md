## DESCRIPTION

*v.trees.param* calculates various tree parameters for tree crowns given
as input vector map **treecrowns**. The module returns following
parameters: tree height, crown area, crown perimeter, NDVI per single
tree, crown volume, stem position, distance to nearest building and
distance to nearest tree. The module takes as input a raster map of the
**ndsm** for computation of the tree height, a raster map of the
**ndvi** for computation of the NDVI per single tree and a vector map of
the **buildings** for computation of the distance to the nearest
building.

Optionally, the parameters **dist_building** and **dist_tree** can be
given, determining the range within neighbouring buildings or trees are
searched for. First the region is set to the tree of interest, then the
region is extended in each direction by **dist_building** or
**dist_tree** (given in meters). By default **dist_building** is unset,
and **dist_tree** is set to 500 m.

The calculation can be done in parallel, with the number of parallel
processes given by **nprocs**.

Additionally the maximum memory to be used can be set by **memory**.

## EXAMPLES

### Example 1: run with standard settings

```sh
v.trees.param ndsm=ndsm ndvi=ndvi buildings=hausumringe treecrowns=trees
```

### Example 2: run with 5 parallel processes

```sh
v.trees.param ndsm=ndsm ndvi=ndvi buildings=hausumringe treecrowns=trees nprocs=5
```

### Example 3: with optional input of **dist_tree** and **dist_building**

```sh
v.trees.param ndsm=ndsm ndvi=ndvi buildings=hausumringe treecrowns=trees dist_tree=500 dist_building=500
```

## SEE ALSO

*[v.trees.param.worker](v.trees.param.worker.md),
[v.to.db](https://grass.osgeo.org/grass-stable/manuals/v.to.db.html),
[v.rast.stats](https://grass.osgeo.org/grass-stable/manuals/v.rast.stats.html),
[r.distance](https://grass.osgeo.org/grass-stable/manuals/r.distance.html),
[v.distance](https://grass.osgeo.org/grass-stable/manuals/v.distance.html)*

## AUTHOR

Lina Krisztian, [mundialis GmbH & Co. KG](https://www.mundialis.de/),
Germany

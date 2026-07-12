## DESCRIPTION

*v.trees.cd* calculates the change between two given treecrown vector
maps (**input** and **reference** for time t1 and t2, respectively).

It returns three vector maps: *&ltbasename&gt_congruent* for congruent
trees, *&ltbasename&gt_only\_&ltinput\>* for gone trees and
*&ltbasename&gt_only\_&ltreference\>* for new trees, with
*&ltbasename\>* defined by **output**. For the congruent trees the
parameter **congr_thresh** can be set, defining the threshold of overlap
(in percentage) above which trees are considered to be congruent. Per
default it is set to 90%.

For the two other maps (gone and new trees) two parameters can be set,
to remove small areas: **diff_min_size** and **diff_max_fd**. They
define the minimum size of identified change areas in sqm (default 0.25
sqm), and the maximum value of fractal dimension of identified change
areas (default 2.5).

The calculation can be done in parallel on a grid, with the edge length
of grid tiles given by **tile_size** and the number of parallel
processes given by **nprocs**.

## EXAMPLE

### Calculate change detection with tile_size of 500

```sh
v.trees.cd input=treecrowns_2020 reference=treecrowns_2022 output=cd_2020_2022 tile_size=500
```

### Calculate change detection with explicit values for filtering congruent and changed maps

```sh
v.trees.cd input=treecrowns_2020 reference=treecrowns_2022 output=cd_2020_2022 congr_thresh=80 diff_min_size=1 tile_size=500
```

## SEE ALSO

*[v.overlay](https://grass.osgeo.org/grass-stable/manuals/v.overlay.html),
[v.trees.cd.worker](v.trees.cd.worker.md)*

## AUTHORS

Julia Haas, [mundialis GmbH & Co. KG](https://www.mundialis.de/),
Germany Lina Krisztian, [mundialis GmbH & Co.
KG](https://www.mundialis.de/), Germany

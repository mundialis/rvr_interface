## DESCRIPTION

*r.trees.mlapply* applies the tree classification model in parallel to
the area of interest (current region). The actual classification is
performed by *r.trees.mlapply.worker*

## SEE ALSO

*[r.learn.ml2](r.learn.ml2.md)*

## EXAMPLES

### Application of the tree classification model in parallel

```sh
r.trees.mlapply model=ml_trees_randomforest.gz \
                group=ml_input \
                area=area_of_interest \
                output=trees_ml_raw \
                tile_size=100 \
                nprocs=2
```

## AUTHOR

Anika Weinmann, Markus Metz, [mundialis GmbH & Co.
KG](https://www.mundialis.de/)

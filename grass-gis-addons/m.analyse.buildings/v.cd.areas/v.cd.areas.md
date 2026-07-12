## DESCRIPTION

*v.cd.areas* calculates differences between two vector layers (e.g.
classification and reference) by making use of v.overlay with operator
"xor".

Only differences with a defined minimum size are extracted. Optionally,
quality measures *completeness* and *correctness* can be calculated.

## EXAMPLE

### Difference between extracted buildings and buildings included in ALKIS using a tile size of 2000m

```sh
v.cd.areas input=extracted_buildings reference=ALKIS_buildings min_size=10 output=difference_buildings tile_size=2000
```

## SEE ALSO

*[v.overlay](https://grass.osgeo.org/grass-stable/manuals/v.overlay.html),
[v.to.db](https://grass.osgeo.org/grass-stable/manuals/v.to.db.html),
[v.db.droprow](https://grass.osgeo.org/grass-stable/manuals/v.db.droprow.html)*

## AUTHOR

Julia Haas, [mundialis GmbH & Co. KG](https://www.mundialis.de/)

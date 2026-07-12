## DESCRIPTION

*v.cd.areas.worker* is a worker module that is started by
[v.cd.areas](v.cd.areas.md). It calculates differences between two
vector layers (e.g. classification and reference) by making use of
v.overlay with operator "xor".

Optionally, quality measures *completeness* and *correctness* can be
calculated.

## SEE ALSO

*[v.overlay](https://grass.osgeo.org/grass-stable/manuals/v.overlay.html),
[v.to.db](https://grass.osgeo.org/grass-stable/manuals/v.to.db.html),
[v.db.droprow](https://grass.osgeo.org/grass-stable/manuals/v.db.droprow.html)*

## AUTHOR

Julia Haas, [mundialis GmbH & Co. KG](https://www.mundialis.de/)

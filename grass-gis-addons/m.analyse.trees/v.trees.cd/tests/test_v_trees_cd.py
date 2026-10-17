"""Tests for the v.trees.cd GRASS addon.

Test groups:
- Interface description validation: required parameters 'congr_thresh' and
  'diff_min_size'
- Change detection between tree input and reference maps:
  - Input contains two tree polygons (one shared at (2,2), one new at (20,20))
  - Reference contains two tree polygons (same shared at (2,2), one old at (15,15))
  - Verifies the addon identifies changes and outputs vectors for trees
    present only in input ("trees_difference_only_tree_objects") and
    only in reference ("trees_difference_only_reference_trees")

SPDX-FileCopyrightText: (c) 2026 by mundialis GmbH & Co. KG
SPDX-FileCopyrightText: (c) 2026 GRASS Development Team
SPDX-License-Identifier: GPL-2.0-or-later
"""

import grass.script as gs

from conftest import (
    create_vector_areas,
    module_interface,
    require_addon,
    vector_exists,
    vector_info,
)


def test_interface(xy_session):
    require_addon("v.trees.cd")
    require_addon("v.trees.cd.worker")
    interface = module_interface("v.trees.cd", xy_session)
    assert interface["congr_thresh"]
    assert interface["diff_min_size"]


def test_change_detection(xy_session, tmp_path):
    # shared tree (2,2), tree only in input (20,20), tree only in
    # reference (15,15)
    create_vector_areas(
        xy_session, tmp_path, "tree_objects", [(2, 2, 8, 8), (20, 20, 26, 26)]
    )
    create_vector_areas(
        xy_session,
        tmp_path,
        "reference_trees",
        [(2, 2, 8, 8), (15, 15, 21, 21)],
    )
    gs.run_command(
        "v.trees.cd",
        input="tree_objects",
        reference="reference_trees",
        congr_thresh=90,
        diff_min_size=0.25,
        diff_max_fd=2.5,
        output="trees_difference",
        tile_size=1000,
        nprocs=1,
        env=xy_session.env,
        # quiet would set GRASS_VERBOSE=0, silencing the stderr message
        # "Output is: <...>" which v.trees.cd parses from its worker
    )
    assert vector_exists(xy_session, "trees_difference_only_tree_objects")
    assert vector_exists(xy_session, "trees_difference_only_reference_trees")
    assert (
        vector_info(xy_session, "trees_difference_only_tree_objects")["areas"]
        > 0
    )

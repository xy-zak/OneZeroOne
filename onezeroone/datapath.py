"""Data path parsing and direct property value application.

:func:`parse_full_data_path` splits a "Copy Full Data Path" string (e.g.
``bpy.data.objects["Cube"].location[0]``) into ``(id_block, data_path,
array_index)`` so we can resolve and set properties programmatically.

:func:`set_property_value` directly mutates the RNA property, bypassing the
depsgraph.  This allows high-frequency updates (limited only by the display
refresh rate) rather than the ~5 Hz depsgraph evaluation cycle that
driver-based updates are throttled to.
"""

from __future__ import annotations

import re

import bpy

_PREFIX_RE = re.compile(r'^bpy\.data\.(\w+)\["([^"]+)"\](?:\.)?(.*)$')
_INDEX_RE = re.compile(r"^(.*)\[(\d+)\]$")

# Match the last component of a data_path for splitting into parent + key.
_LAST_ID_RE = re.compile(r'^(.*)\["([^"]+)"\]$')
_LAST_RNA_RE = re.compile(r"^(.*)\.(\w+)$")


def split_full_data_path(full_path: str):
    """Split a full data path into (collection, name, rna_path, index_or_none).

    ``index`` is an int when the path ends in ``[n]`` (including ``[0]``),
    otherwise ``None`` for scalars. Returns ``None`` if the prefix is not a
    ``bpy.data.<collection>["name"]`` path. Does not look up Blender IDs.
    """
    m = _PREFIX_RE.match(full_path)
    if not m:
        return None
    coll_name, item_name, remainder = m.groups()
    m2 = _INDEX_RE.match(remainder)
    if m2:
        return coll_name, item_name, m2.group(1), int(m2.group(2))
    return coll_name, item_name, remainder, None


def short_data_path(full_path: str) -> str:
    """Short label for the N-panel, e.g. ``Cube.location[0]``."""
    parts = split_full_data_path(full_path)
    if parts is None:
        if len(full_path) <= 42:
            return full_path
        return "…" + full_path[-41:]
    _coll, name, rna, index = parts
    if rna.startswith("["):
        body = f"{name}{rna}"
    elif rna:
        body = f"{name}.{rna}"
    else:
        body = name
    if index is not None:
        body = f"{body}[{index}]"
    return body


def parse_full_data_path(full_path: str):
    """Parse a "Copy Full Data Path" string into (id_block, data_path, index).

    Examples:
        bpy.data.objects["Cube"].location[0]      -> (obj, "location", 0)
        bpy.data.objects["Cube"]["my_prop"]       -> (obj, '["my_prop"]', None)
        bpy.data.objects["Arm"].pose.bones["Bone"].location[2]
                                                   -> (arm, 'pose.bones["Bone"].location', 2)

    Returns (None, None, None) if parsing fails. ``index`` is ``None`` for
    scalars so callers can distinguish ``location[0]`` from a non-array path.
    """
    parts = split_full_data_path(full_path)
    if parts is None:
        return None, None, None
    coll_name, item_name, data_path, index = parts
    collection = getattr(bpy.data, coll_name, None)
    if collection is None:
        return None, None, None
    id_block = collection.get(item_name)
    if id_block is None:
        return None, None, None
    return id_block, data_path, index


def set_property_value(id_block, data_path: str, index: int | None, value: float) -> bool:
    """Directly set a property value via RNA mutation (bypasses depsgraph).

    Returns True on success, False if the property could not be set.
    """
    if not data_path:
        return False
    try:
        # Array property: path_resolve returns a mutable reference (Vector,
        # color, etc.) so we can set the element directly.
        prop = id_block.path_resolve(data_path)
        if hasattr(prop, "__setitem__"):
            prop[0 if index is None else index] = value
            return True
    except Exception:  # noqa: BLE001 - fall through to scalar path
        pass

    # Scalar property: path_resolve returned a copy, so set via the parent.
    try:
        # ID property at the end of the path: ["key"]
        m = _LAST_ID_RE.match(data_path)
        if m:
            parent_path, key = m.group(1), m.group(2)
            if parent_path:
                if parent_path.endswith("."):
                    parent_path = parent_path[:-1]
                parent = id_block.path_resolve(parent_path)
            else:
                parent = id_block
            parent[key] = value
            return True

        # RNA property at the end of the path: .attr
        m = _LAST_RNA_RE.match(data_path)
        if m:
            parent_path, attr = m.group(1), m.group(2)
            if parent_path:
                parent = id_block.path_resolve(parent_path)
            else:
                parent = id_block
            setattr(parent, attr, value)
            return True

        # Top-level scalar on id_block
        setattr(id_block, data_path, value)
        return True
    except Exception:  # noqa: BLE001 - property not settable
        return False

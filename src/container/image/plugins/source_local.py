"""source_local.py - Test source plugin: ordered local layers (spec 023).

The host bind-mounts every layer read-only under /home/pwuser/layers/ and
describes them in TEST_ARTIFACT_LAYERS (JSON, contracts/container-io.md §2).
Archive layers are extracted safely into a staging dir; then all layers are
merged in order into the writable per-run test tree (dest_path). Whether
the tree contains tests is decided by run.py per run mode.
"""

import json
import logging
import os
from typing import List, Optional

from _layers import LayerError, merge_layers, safe_extract

logger = logging.getLogger("source_local")

_STAGING_ROOT = "/home/pwuser/.cep-staging"


_LAYER_FIELDS = {"position": int, "host_path": str, "type": str, "container_path": str}


def parse_layer_records(raw: Optional[str]) -> List[dict]:
    """Decode and validate the host's layer list (contracts/container-io.md §2)."""
    try:
        layers = json.loads(raw or "")
    except ValueError:
        layers = None
    valid = isinstance(layers, list) and all(
        isinstance(layer, dict)
        and all(isinstance(layer.get(k), t) for k, t in _LAYER_FIELDS.items())
        for layer in layers)
    if not valid:
        raise RuntimeError("TEST_ARTIFACT_LAYERS missing or invalid")
    return layers


def acquire_tests(_test_name: str, dest_path: str, deadline: float) -> None:
    """Merge the layers from TEST_ARTIFACT_LAYERS into dest_path.

    Args:
        _test_name: Unused — the layers are described by TEST_ARTIFACT_LAYERS
        dest_path: The check root (/home/pwuser/tests)
        deadline: Absolute epoch seconds; passing it raises LayerTimeout

    Raises:
        RuntimeError / LayerError: naming `layer #N (<host_path>)`
    """
    roots = []
    for layer in parse_layer_records(os.environ.get("TEST_ARTIFACT_LAYERS")):
        position = layer["position"]
        label = f"layer #{position} ({layer['host_path']})"
        container_path = layer["container_path"]
        if layer["type"] == "archive":
            if not os.path.isfile(container_path):
                raise LayerError(f"{label}: archive not found in container")
            staged = os.path.join(_STAGING_ROOT, f"{position:02d}")
            safe_extract(container_path, staged, label, deadline)
            roots.append((position, staged, label))
        else:
            if not os.path.isdir(container_path):
                raise LayerError(f"{label}: directory not found in container")
            roots.append((position, container_path, label))

    for override in merge_layers(roots, dest_path, deadline):
        logger.debug("override: %s layer %d wins over layer %d", override.relpath,
                     override.winner_position, override.loser_position)

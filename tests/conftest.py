"""Import the repo AS `household_state` before any test touches it.

Same problem the hassfest job in validate.yml solves and for the same reason:
this repo keeps the integration at its ROOT (hacs.json `content_in_root`)
because jrackerby/HA submodules it AS `custom_components/household_state`.
The directory on disk is `household-state`, which is not an importable module
name, so a test importing `household_state` has to be handed the layout HA
gives it. A symlink in a temp dir does that without restructuring the repo
and breaking the submodule path.
"""

import atexit
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_stage = Path(tempfile.mkdtemp(prefix="household_state_test_"))
atexit.register(shutil.rmtree, _stage, True)
(_stage / "household_state").symlink_to(ROOT, target_is_directory=True)

sys.path.insert(0, str(_stage))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ha_stubs  # noqa: E402

ha_stubs.install()

# A gate that could not run is not a pass: prove the staging actually resolves
# before a single test reports green over an import that never happened.
import household_state.coordinator  # noqa: E402,F401

"""HeLab's second set of bundled plots ("Basic plots v2"), imported normally (not scanned from a
folder) so that packaged builds include them; the Scripts panel registers ``MODULES`` before the
first set's (``helab.scripts.standard``), which stays exactly as it was. Their analysis ids are
``helab.v2.*``, so no result or preset of the first set is taken for theirs."""
from types import ModuleType
from typing import Tuple

MODULES: Tuple[ModuleType, ...] = ()

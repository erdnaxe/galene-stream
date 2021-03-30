# Copyright (C) 2021 Alexandre Iooss
# SPDX-License-Identifier: MIT

"""
Galène stream gateway.
"""

try:
    from galene_stream.version import version as __version__
except ImportError:
    __version__ = "dev"

# See https://www.python.org/dev/peps/pep-0008/#module-level-dunder-names
__all__ = [
    "__version__",
]

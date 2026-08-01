"""Public API for matchify."""

from .assumptions import Assumptions
from .cli import collect_python_files, convert_file
from .transform import IfToMatchTransformer, transform_code

__all__ = [
    "IfToMatchTransformer",
    "Assumptions",
    "collect_python_files",
    "convert_file",
    "transform_code",
]

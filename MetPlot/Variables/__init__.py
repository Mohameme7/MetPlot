import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def catalog_path(model: str, filename: str) -> str:
    """Absolute path to a bundled catalog file, e.g. catalog_path('GEM', 'MERGED_PARAMS.json')."""
    return os.path.join(_HERE, model, filename)
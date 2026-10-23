"""RazerLite : un Polychromatic maison pour Windows, sans Synapse."""

__version__ = "0.5.0"

try:  # numéro de version fixé par le build automatique (voir .github/workflows/release.yml)
    from ._build import VERSION as __version__  # noqa: F811
except ImportError:
    pass

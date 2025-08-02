# tgmix/__init__.py
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("tgmix")
except PackageNotFoundError:
    # Package is not installed yet, e.g., when running locally
    __version__ = "0.0.0-dev"

__author__ = "damnkrat"

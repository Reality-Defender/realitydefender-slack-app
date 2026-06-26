from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from reality_defender_slack_app.app import create_app

try:
    __version__ = version("reality-defender-slack-app")
except PackageNotFoundError:  # package is not installed (e.g. raw source checkout)
    __version__ = "0.0.0+unknown"

__all__ = ["create_app", "__version__"]

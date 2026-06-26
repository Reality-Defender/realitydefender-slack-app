from __future__ import annotations

import uvicorn

from reality_defender_slack_app.app import create_app
from reality_defender_slack_app.config import get_settings, setup_logging


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    app = create_app(settings)
    uvicorn.run(app, host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()

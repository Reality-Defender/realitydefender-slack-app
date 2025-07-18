FROM ghcr.io/astral-sh/uv:python3.12-alpine

ENV SLACK_BOT_TOKEN=""
ENV SLACK_APP_TOKEN=""

ADD . /app

WORKDIR /app
RUN uv sync --locked

# Run the application
CMD ["uv", "run", "./src/slack_app/__init__.py"]

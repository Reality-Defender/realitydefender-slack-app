# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Run as a non-root user in the final image.
RUN groupadd --system --gid 999 nonroot \
 && useradd --system --gid 999 --uid 999 --create-home nonroot

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install dependencies in their own cached layer, before app code.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

# Copy the project and install the rd-slack-app console script.
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Writable dir for the file-based OAuth stores (replaced by DynamoDB later).
RUN mkdir -p /app/data && chown -R nonroot:nonroot /app/data

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 3000
USER nonroot
CMD ["rd-slack-app"]

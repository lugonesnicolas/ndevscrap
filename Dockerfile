FROM ghcr.io/astral-sh/uv:0.12.18 AS uv

FROM python:3.12-slim

COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["ndevscrap"]

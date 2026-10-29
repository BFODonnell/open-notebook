# Isolated experiment image; does not build or alter the application.
FROM ghcr.io/astral-sh/uv:0.8.3-python3.12-bookworm-slim@sha256:74b8fe8ec5931f3930cfb6c87b46aeb1dbd497a609f6abf860fd0f4390f8b040
WORKDIR /proof
COPY scripts/databridge_p0/pyproject.toml scripts/databridge_p0/uv.lock ./
RUN uv sync --frozen
COPY scripts/databridge_p0/motherduck/pyproject.toml scripts/databridge_p0/motherduck/uv.lock ./motherduck/
RUN uv sync --project motherduck --frozen
COPY scripts/databridge_p0/duckdb_concurrency.py ./
ENV TMPDIR=/proof-data
RUN mkdir /proof-data
CMD ["uv", "run", "--frozen", "python", "duckdb_concurrency.py"]

FROM python:3.13-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

RUN uv pip install -e . --no-deps

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "bud.main:app", "--host", "0.0.0.0", "--port", "8000"]

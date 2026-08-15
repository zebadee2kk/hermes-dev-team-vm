FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 forge
USER forge

EXPOSE 8080
CMD ["uvicorn", "forge_controller.api:app", "--host", "0.0.0.0", "--port", "8080"]

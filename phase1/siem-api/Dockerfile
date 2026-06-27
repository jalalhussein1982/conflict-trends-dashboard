FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY static ./static

RUN pip install --no-cache-dir .

EXPOSE 80

CMD ["uvicorn", "siem_api.main:app_factory", "--factory", "--host", "0.0.0.0", "--port", "80", "--app-dir", "src"]


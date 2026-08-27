FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY packs ./packs
COPY evaluations ./evaluations
RUN pip install --no-cache-dir .
ENV STYLEOS_REPOSITORY_ROOT=/app STYLEOS_HOME=/data
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "styleos.api:app", "--host", "0.0.0.0", "--port", "8000"]

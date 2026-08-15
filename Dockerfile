# AENIMUS studio image v0.1.0
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
COPY app ./app
RUN pip install --no-cache-dir .
COPY personas ./personas
RUN useradd --create-home --uid 10001 aenimus && mkdir -p /data /workspace && chown -R aenimus:aenimus /data /workspace /app
USER aenimus
ENV AENIMUS_HOST=0.0.0.0 AENIMUS_PORT=8787 AENIMUS_DATA_DIR=/data AENIMUS_WORKSPACE=/workspace
EXPOSE 8787
CMD ["python", "-m", "app.main"]

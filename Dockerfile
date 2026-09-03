FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY agentops ./agentops
COPY apps/web ./apps/web
RUN pip install --no-cache-dir .
ENV AGENTOPS_DB_PATH=/data/agentops.db
RUN mkdir /data
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"
CMD ["uvicorn", "agentops.api:app", "--host", "0.0.0.0", "--port", "8000"]


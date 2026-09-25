FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Install the CPU-only PyTorch wheel *before* the rest of requirements.txt. Otherwise
# pip resolves sentence-transformers' torch dependency from PyPI's default index,
# which serves the full CUDA-enabled build (multiple GB) even though this container
# has no GPU and will never use one — observed firsthand as several hundred MB of
# build cache accumulating during the very first image build. Installing the CPU
# wheel first satisfies the dependency before pip ever considers the GPU one.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# Uses Python's own stdlib rather than curl/wget specifically to avoid adding a
# package to the image just for this — python:3.11-slim already has everything
# this needs. --start-period allows for the embedding-model cold-start latency
# documented in docs/LIMITATIONS.md (first RAG call can take 30-45s).
HEALTHCHECK --interval=15s --timeout=5s --start-period=45s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

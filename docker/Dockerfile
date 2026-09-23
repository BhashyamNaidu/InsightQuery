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

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

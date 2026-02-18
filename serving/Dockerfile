# Container para Cloud Run — inferência CPU do DistilBERT
FROM python:3.11-slim

WORKDIR /app

# Instala dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instala dependências Python (PyTorch CPU — container menor)
COPY serving/requirements.txt .
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    torch==2.2.0 && \
    pip install --no-cache-dir \
    fastapi==0.111.0 \
    uvicorn==0.30.1 \
    pydantic==2.7.1 \
    transformers==4.40.0 \
    safetensors==0.4.3

# Copia o modelo treinado para dentro do container
COPY model/model/ ./model/

# Copia o código da API
COPY serving/app.py .

# Usuário não-root
RUN useradd -m appuser
USER appuser

# Cloud Run usa porta 8080
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Inicia o servidor
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]

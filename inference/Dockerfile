# vLLM pré-instalado + nosso script de labeling
FROM vllm/vllm-openai:latest

# Symlink python -> python3 (image base só tem python3)
RUN ln -sf /usr/bin/python3 /usr/local/bin/python || true

# Dependências extras pra GCS + parquet
RUN pip install --no-cache-dir \
    google-cloud-storage>=2.16.0 \
    pandas>=2.2.0 \
    pyarrow>=15.0.0

# Copia script
COPY labeling_pipeline.py /app/labeling_pipeline.py

WORKDIR /app
ENTRYPOINT ["python3", "/app/labeling_pipeline.py"]

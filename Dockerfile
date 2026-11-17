FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chmod=644 server.py upstream.py .
USER 65534:65534
EXPOSE 8000
CMD ["python", "server.py"]

FROM python:3.12-slim
WORKDIR /app
COPY simulador/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY simulador/simulador.py .
USER 10001
ENTRYPOINT ["python", "-u", "simulador.py"]

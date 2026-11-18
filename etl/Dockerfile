FROM python:3.12-slim
WORKDIR /app
COPY etl/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY etl/etl.py .
COPY sql/ /app/sql/
USER 10001
ENTRYPOINT ["python", "-u", "etl.py"]

FROM python:3.8-slim

WORKDIR /app
RUN pip install --no-cache-dir python-consul
COPY . /app

CMD ["python", "init.py"]

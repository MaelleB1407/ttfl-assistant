FROM python:3.11-slim

WORKDIR /app

COPY ../requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY . .

ENV DB_DSN="postgresql://ttfl:ttfl@postgres:5432/ttfl_database"

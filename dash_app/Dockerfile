FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# ⬇️ On corrige ici
COPY dash_app/dash_app.py .
COPY common ./common

ENV DB_DSN="postgresql://ttfl:ttfl@postgres:5432/ttfl_database"

EXPOSE 8050
CMD ["python", "dash_app.py"]

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# ⬇️ On corrige ici
COPY dash_app/dash_app.py .

ENV DB_DSN="postgresql://injuries:injuries@postgres:5432/injuries"

EXPOSE 8050
CMD ["python", "dash_app.py"]

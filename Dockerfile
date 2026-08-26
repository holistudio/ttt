FROM python:3.11-slim

WORKDIR /code

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
COPY frontend frontend

WORKDIR /code/backend

EXPOSE 5000

CMD ["python", "app.py"]

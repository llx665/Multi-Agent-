FROM python:3.10-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl git && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && apt-get install -y nodejs && rm -rf /var/lib/apt/lists/*
COPY . .
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir -r backend/requirements.txt
RUN pip install --no-cache-dir psycopg2-binary==2.9.10 gunicorn==23.0.0
WORKDIR /app/frontend
RUN npm install && npm run build || echo "Frontend build skipped"
WORKDIR /app
EXPOSE 8080
CMD ["uvicorn", "backend.render_start:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]

FROM node:20-alpine AS webbuild
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=webbuild /web/dist ./frontend_dist
RUN mkdir -p /app/data
EXPOSE 5051
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "5051"]

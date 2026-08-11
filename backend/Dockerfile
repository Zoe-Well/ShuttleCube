FROM python:3.14-slim
WORKDIR /app
COPY backend /app
RUN pip install --no-cache-dir .
CMD ["uvicorn", "shuttlecube.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

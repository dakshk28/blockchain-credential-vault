FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY . .
RUN useradd --create-home appuser && mkdir -p /var/lib/acv/uploads && chown -R appuser /app /var/lib/acv
USER appuser
ENV FLASK_ENV=production UPLOAD_DIRECTORY=/var/lib/acv/uploads
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app:app"]

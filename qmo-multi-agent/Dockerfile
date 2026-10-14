FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY qmo ./qmo
RUN useradd --create-home qmo && chown -R qmo:qmo /app
USER qmo
EXPOSE 8000
CMD ["uvicorn", "qmo.main:app", "--host", "0.0.0.0", "--port", "8000"]

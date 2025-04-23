FROM python:3.9-slim

WORKDIR /app

ENV FLASK_APP=app.py
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Ensure proper line endings for Windows compatibility
RUN apt-get update && apt-get install -y dos2unix && \
    dos2unix app.py && \
    apt-get remove -y dos2unix && apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

CMD ["flask", "run", "--host=0.0.0.0", "--port=5001"]

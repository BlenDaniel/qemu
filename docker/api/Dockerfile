FROM python:3.13-slim

WORKDIR /app

ENV FLASK_APP=app.py
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

CMD ["flask", "run", "--host=0.0.0.0", "--port=5001"]

FROM python:3.9-slim

WORKDIR /usr/src/app

COPY . .

# Install other requirements
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 80

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

CMD ["python", "main.py"]

FROM python:3.13-slim

RUN mkdir /app

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN pip install --upgrade pip

COPY requirements.txt /app/

RUN pip install --no-cache-dir -r requirements.txt

COPY ./footballcafe /app

COPY ./scripts /scripts

RUN chmod +x /scripts/run.sh /scripts/rundev.sh

EXPOSE 8000

ENV PATH="/scripts:$PATH"

# DEV=true runs Django's own server with live reload; anything else runs gunicorn.
CMD if [ "$DEV" = "true" ]; then rundev.sh; else run.sh; fi

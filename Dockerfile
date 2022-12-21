FROM python:3.10-slim-buster
RUN apt-get update && apt-get -y install cron

WORKDIR /app

COPY requirements.txt main.py my_secrets.py /app/
COPY crontab /etc/cron.d/crontab

RUN pip install -r requirements.txt

RUN chmod 0644 /etc/cron.d/crontab
RUN /usr/bin/crontab /etc/cron.d/crontab

# run crond as main process of container
CMD ["cron", "-f"]
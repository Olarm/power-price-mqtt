FROM python:3.10-slim-buster
RUN apt-get update && apt-get -y install apt-utils cron 

WORKDIR /app

COPY requirements.txt main.py /app/
RUN pip install -r requirements.txt

COPY crontab /etc/cron.d/crontab
RUN chmod 0644 /etc/cron.d/crontab
RUN crontab /etc/cron.d/crontab
RUN touch /var/log/cron.log

# run crond as main process of container
#CMD ["cron", "-f"]
CMD cron && tail -f /var/log/cron.log

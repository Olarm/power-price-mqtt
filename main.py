#!/usr/bin/env python3

import requests
import datetime
import json, toml
from entsoe import EntsoePandasClient
import pandas as pd
import paho.mqtt.publish as publish
import paho.mqtt.client as mqtt
import os
import signal


import logging
from sys import stdout

#from my_secrets import *

# Define logger
logger = logging.getLogger('power_price')

logger.setLevel(logging.DEBUG) # set logger level
logFormatter = logging.Formatter\
("%(name)-12s %(asctime)s %(levelname)-8s %(filename)s:%(funcName)s %(message)s")
consoleHandler = logging.StreamHandler(stdout) #set streamhandler to stdout
consoleHandler.setFormatter(logFormatter)
logger.addHandler(consoleHandler)


class PowerControl():
    def __init__(self, *args, **kwargs):
        logger.info("Starting power_price")
        self.conversion_ts = None
        self.eur_nok = None
        self.read_config()
        self.get_eur_nok_conversion()
        self.publish()


    def read_config(self):
        try:
            self.config = toml.load("/app/config.toml")
        except Exception as e:
            logger.error(f"Failed to read config file with: {e}")
            #os.kill(os.getppid(), signal.SIGTERM)
        logger.info(f"config: {self.config}")


    def publish(self):
        df = self.get_day_ahead(supplier="lyse")
        price_mean = df["price"].mean()
        ts = pd.Timestamp(datetime.datetime.now(), tz="Europe/Oslo")
        price_now = df[df["time"] < ts]["price"].iloc[0]
        payload = {
            "ts": str(ts), 
            "price_now": price_now, 
            "price_mean": price_mean,
            "price_below_mean": "true" if price_now < price_mean else "false"
        }

        logger.info(f"Publishing: {payload}")
        publish.single("power_price", payload=json.dumps(payload), qos=0, retain=False, hostname=self.config.get("HOST"),
            port=1883, client_id="", keepalive=60, will=None, auth=None, tls=None,
            protocol=mqtt.MQTTv311, transport="tcp")


    def get_eur_nok_conversion(self):
        if self.eur_nok != None and self.conversion_ts != None:
            if self.conversion_ts > pd.Timestamp(datetime.date.today() - datetime.timedelta(hours=24), tz="Europe/Oslo"):
                return

        exchange_token = self.config.get("EXCHANGE_TOKEN")
        response = requests.get(f"https://v6.exchangerate-api.com/v6/{exchange_token}/latest/eur")
        if response.ok:
            body_json = response.json()
            rates = body_json.get("conversion_rates")
            nok = rates.get("NOK")
            self.eur_nok = nok
            self.conversion_ts = pd.Timestamp(datetime.datetime.now(), tz="Europe/Oslo")
            return
        else:
            logger.error("Could not get conversion rate")


    def get_zone(self, client, zone, start, end, supplier):
        data = client.query_day_ahead_prices(zone, start=start, end=end)
        self.get_eur_nok_conversion()
        if self.eur_nok:
            data *= self.eur_nok
        else:
            logger.warning("Dont have conversion rate, using 10.5...")
        data *= 1e-1    # øre per kWh
        if supplier == "tibber":
            data += 1.0     # paslag 1.0 øre/kWh
        elif supplier == "lyse":
            data += 3.2     # paslag 3.2 øre/kWh
        data *= 1.25    # moms 25%

        zone = [zone] * data.size
        df = pd.DataFrame({"time":data.index, "price":data.values, "zone":zone})
        return df


    def get_day_ahead(self, zones=["NO_2"], supplier="tibber"):
        client = EntsoePandasClient(api_key=self.config.get("ENTSOE_TOKEN"))
        start = pd.Timestamp(datetime.date.today(), tz="Europe/Oslo")
        end = pd.Timestamp(datetime.date.today() + datetime.timedelta(days=3), tz="Europe/Oslo")

        df = pd.DataFrame(columns=["time", "price", "zone"])
        for zone in zones:
            temp_df = self.get_zone(client, zone, start, end, supplier)
            df = pd.concat([df, temp_df])

        return df


if __name__ == "__main__":
    logger.info(f"Running script at {datetime.datetime.now()}")
    try:
        PowerControl()
    except Exception as e:
        logger.error(f"{e}")
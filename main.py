import requests
import datetime
import json
from entsoe import EntsoePandasClient
import pandas as pd
import paho.mqtt.client as mqtt

import logging
from sys import stdout

from secrets import *

# Define logger
logger = logging.getLogger('power_price')

logger.setLevel(logging.DEBUG) # set logger level
logFormatter = logging.Formatter\
("%(name)-12s %(asctime)s %(levelname)-8s %(filename)s:%(funcName)s %(message)s")
consoleHandler = logging.StreamHandler(stdout) #set streamhandler to stdout
consoleHandler.setFormatter(logFormatter)
logger.addHandler(consoleHandler)


class PowerControl():
    def initialize(self):
        self.conversion_ts = None
        self.eur_nok = None
        self.get_eur_nok_conversion()
        self.publish()


    def publish(self, kwargs):
        df = self.get_day_ahead(supplier="lyse")
        price_mean = df["price"].mean()
        ts = pd.Timestamp(datetime.datetime.now(), tz="Europe/Oslo")
        price_now = df[df["time"] < ts]["price"].iloc[0]
        payload = {
            ts: ts, 
            price_now: price_now, 
            price_mean: price_mean,
        }

        mqtt.single("power_price", payload=payload, qos=0, retain=False, hostname="localhost",
            port=1883, client_id="", keepalive=60, will=None, auth=None, tls=None,
            protocol=mqtt.MQTTv311, transport="tcp")


    def get_eur_nok_conversion(self):
        if self.EUR_NOK != None and self.conversion_ts != None:
            if self.conversion_ts > pd.Timestamp(datetime.date.today() - datetime.timedelta(hours=1), tz="Europe/Oslo"):
                return

        response = requests.get(f"https://v6.exchangerate-api.com/v6/{EXCHANGE_TOKEN}/latest/eur")
        if response.ok:
            body_json = response.json()
            rates = body_json.get("conversion_rates")
            nok = rates.get("NOK")
            self.EUR_NOK = nok
            self.conversion_ts = pd.Timestamp(datetime.datetime.now(), tz="Europe/Oslo")
            return


    def get_zone(self, client, zone, start, end, supplier):
        data = client.query_day_ahead_prices(zone, start=start, end=end)
        self.get_eur_nok_conversion()
        data *= self.nok_eur
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
        client = EntsoePandasClient(api_key=ENTSOE_TOKEN)
        start = pd.Timestamp(datetime.date.today(), tz="Europe/Oslo")
        end = pd.Timestamp(datetime.date.today() + datetime.timedelta(days=3), tz="Europe/Oslo")

        df = pd.DataFrame(columns=["time", "price", "zone"])
        for zone in zones:
            temp_df = self.get_zone(client, zone, start, end, supplier)
            df = pd.concat([df, temp_df])

        return df


if __name__ == "__main__":
    logger.info(f"Running script at {datetime.now()}")
    try:
        PowerControl()
        logger.info("Successfully published power price.")
    except Exception as e:
        logger.error(f"{e}")
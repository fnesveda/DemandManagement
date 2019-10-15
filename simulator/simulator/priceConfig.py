#!/usr/bin/env python3

import json
import os

from types import SimpleNamespace

thisDir = os.path.dirname(__file__)

# load the config from a file
with open(f"{thisDir}/data/manual/priceConfig.json", "r") as priceConfigFile:
	priceConfig = json.load(priceConfigFile, object_hook=lambda dct: SimpleNamespace(**dct))

# length of each interval of cheap electricity price
cheapIntervalLength = priceConfig.cheapIntervalLength
# minimum minutes the electricity price will be cheaper each day
cheapMinutesCount = priceConfig.cheapMinutesCount

# the electricity prices [money per kWh]
lowerPrice = priceConfig.lowerPrice
higherPrice = priceConfig.higherPrice

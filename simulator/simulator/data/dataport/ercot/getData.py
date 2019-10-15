#!/usr/bin/env python3

import math
import os
import sys

import pandas
import sqlalchemy

fromDate = sys.argv[1]
toDate = sys.argv[2]
username = sys.argv[3]
password = sys.argv[4]

print("Downloading ERCOT actual demand data...")

# create the postgresql connection engine
engine = sqlalchemy.create_engine(f"postgresql://{username}:{password}@dataport.pecanstreet.org:5434/dataport")

# download the actual power demand information
query = f'''
	SELECT delivery_date at time zone 'CST' as deliverydate, 1000*min(demand) as demand
	FROM ercot.system_wide_demand
	WHERE delivery_date >= '{fromDate}'
	AND delivery_date < '{toDate}'
	GROUP BY delivery_date
'''
data = pandas.read_sql_query(query, con=engine, parse_dates=["deliverydate"])

print("Parsing...")
# resample the time series to minutes and interpolate the missing values
data = data.set_index(["deliverydate"]).resample('min').interpolate('cubic')

# save the resampled demand to a CSV file
os.makedirs("actual", exist_ok=True)
data.to_csv("actual/systemLoad.csv")

print("Done.")

# download the power demand predictions
print("Downloading ERCOT predicted demand data...")
query = f'''
	SELECT report_date at time zone 'CST' as reportdate, delivery_date at time zone 'CST' as deliverydate, 1000*system_total as demand
	FROM ercot.load_forecast_xforecast_zone_7day
	WHERE delivery_date >= '{fromDate}'
	AND delivery_date < '{toDate}'
'''
data = pandas.read_sql_query(query, con=engine, parse_dates=["reportdate", "deliverydate"])

# dispose of the engine (sometimes the connection keeps hanging otherwise, even after the script has finished)
engine.dispose()

print("Parsing...")

os.makedirs("predictions", exist_ok=True)

# from all the predictions that were made for a date, get the one which is the right time ahead
def getPrediction(group, td) -> float:
	closestPrediction = 0.0
	closestPredictionDistance = math.inf
	for _, row in group.iterrows():
		predictionDistance = (row["deliverydate"] - row["reportdate"]).total_seconds() // 3600
		if abs(predictionDistance - td) < abs(closestPredictionDistance - td):
			closestPrediction = row["demand"]
			closestPredictionDistance = predictionDistance
	return closestPrediction

# for each date that was predicted, get the predictions which were exactly 0, 1, 2, 3, 4 or 5 days ahead
groupby = data.groupby("deliverydate")
for hoursAhead in [0, 24, 48, 72, 96, 120]:
	# get the predictions, smooth them out a bit, resample the resulting time series to minutes and interpolate the missing values
	predictions = groupby.apply(getPrediction, hoursAhead).rolling(window=3, center=True, min_periods=1).mean().resample('min').interpolate('cubic')
	# save the predictions to a CSV file
	predictions.to_csv(f"predictions/{hoursAhead}.csv", header=["demand"])

print("Done.")

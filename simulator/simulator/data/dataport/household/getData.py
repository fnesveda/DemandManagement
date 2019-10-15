#!/usr/bin/env python3

import sys

import pandas
import sqlalchemy

fromDate = sys.argv[1]
toDate = sys.argv[2]
username = sys.argv[3]
password = sys.argv[4]

print(f"Downloading household data...")

# create the postgresql connection engine
engine = sqlalchemy.create_engine(f"postgresql://{username}:{password}@dataport.pecanstreet.org:5434/dataport")

# download the household IDs which have some valid data
query = f'''
	SELECT DISTINCT dataid
	FROM electricity.eg_realpower_15min
	WHERE grid IS NOT NULL
	AND grid > 0.05
	AND local_15min >= '{fromDate}'
	AND local_15min < '{toDate}'
'''
dataIDs = pandas.read_sql_query(query, con=engine).fillna(0)

# this household has weird, invalid data around June 20, 2018, so we throw it out
badIDs = [6730]
validIDs = [id for id in dataIDs["dataid"] if id not in badIDs]
idFilter = ', '.join(map(str, validIDs))

# download the average power draw of the selected households for each minute in the interval
query = f'''
	SELECT localminute at time zone 'CST' as localminute, AVG(COALESCE(solar, 0) + COALESCE(solar2, 0) + COALESCE(grid, 0)) as use
	FROM electricity.eg_realpower_1min
	WHERE dataid IN ({idFilter})
	AND localminute >= '{fromDate}'
	AND localminute < '{toDate}'
	GROUP BY localminute
	ORDER BY localminute
'''
data = pandas.read_sql_query(query, con=engine, parse_dates=[0]).fillna(0)

# smooth out the data a bit, interpolate the power draw and save it to CSV
averageDraw = data.set_index("localminute").resample('min').interpolate('time').rolling(window=120, center=True, min_periods=1).mean()
averageDraw.to_csv(f"averageDraw.csv", index_label="datetime", header=["draw"], float_format="%.5f")

print("Done.")

# dispose of the engine (sometimes the connection keeps hanging otherwise, even after the script has finished)
engine.dispose()

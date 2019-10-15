#!/usr/bin/env python3

import sys

from collections import defaultdict
from typing import List

import numpy
import pandas
import sqlalchemy

fromDate = sys.argv[1]
toDate = sys.argv[2]
username = sys.argv[3]
password = sys.argv[4]

print("Downloading dataport car data...", flush=True)
# create the postgresql connection engine
engine = sqlalchemy.create_engine(f"postgresql://{username}:{password}@dataport.pecanstreet.org:5434/dataport")

# download the data power draw data from the database
# we only need the sums for each charging interval, so an 1-hour resolution is enough
query = f'''
	SELECT dataid, local_15min at time zone 'CST' as local_15min, car1
	FROM electricity.eg_realpower_15min
	WHERE local_15min >= '{fromDate}'
	AND local_15min < '{toDate}'
	AND "dataid" = ANY(
		SELECT DISTINCT dataid
		FROM electricity.eg_realpower_15min
		WHERE car1 IS NOT NULL
		AND car1 > 0.1
		AND local_15min >= '{fromDate}'
		AND local_15min < '{toDate}'
	)
	ORDER BY dataid, local_15min
'''
data = pandas.read_sql_query(query, con=engine, parse_dates=["local_15min"]).fillna(0)

# dispose of the engine (sometimes the connection keeps hanging otherwise, even after the script has finished)
engine.dispose()

# parse the downloaded data
print("Parsing...")
groups = data.groupby("dataid")

# for each car get the continuous charging intervals
# add up how much electricity did the charging consume in total in each interval
# the data is sampled in kW in 15 minute intervals, to convert it to kWh, we need to divide it by four
def getSums(df) -> List[float]:
	sums = []
	startingDate = None
	workingSum = 0
	for localhour, carDraw in df.itertuples(index=False):
		if carDraw < 0.1:
			if workingSum > 0.5:
				sums.append((startingDate, workingSum))
			workingSum = 0
			startingDate = None
		else:
			if startingDate is None:
				startingDate = localhour.date()
			workingSum += carDraw / 4.0
	return sums

# group the charging sums by date into a dictionary
charges = defaultdict(list)
for chargeSums in groups.apply(getSums).values:
	for date, charge in sorted(list(chargeSums)):
		charges[date].append(charge)

# write the charging sums out into a file, each day on one line
with open("charges.txt", "w") as chargesFile:
	for date, chargesOnDate in sorted(charges.items()):
		chargesFile.write(f"{date}: {chargesOnDate}\n")

# get the maximum charging power the charger was drawing for each car
maxChargingPowers = groups["car1"].max().values

# save it into a file
numpy.savetxt("maxPowers.txt", maxChargingPowers, fmt="%.5f")

print("Done.")

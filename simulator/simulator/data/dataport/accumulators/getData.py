#!/usr/bin/env python3

import os
import sys

import numpy
import pandas
import sqlalchemy

fromDate = sys.argv[1]
toDate = sys.argv[2]
username = sys.argv[3]
password = sys.argv[4]

# create the postgresql connection engine
engine = sqlalchemy.create_engine(f"postgresql://{username}:{password}@dataport.pecanstreet.org:5434/dataport")

# download the data for each appliance type
for columnID, outFolder in [("refrigerator1", "fridge"), ("furnace1", "electricalheating"), ("air1", "airconditioning"), ("waterheater1", "waterheater")]:
	print(f"Downloading {outFolder} data...")
	os.makedirs(outFolder, exist_ok=True)
	
	badIDs = []
	# these households already have a grid-controlled water heater, which would pollute our data, so we filter them out
	if columnID == "waterheater1":
		badIDs = [2171, 2204, 5357, 7937, 9356, 9934]
	
	# these households have bad data for their electrical heating, which causes errors in the simulation
	if columnID == "furnace1":
		badIDs = [6730, 7536, 7901, 9019]
	
	# these households have bad data for their air conditioning, which causes errors in the simulation
	if columnID == "air1":
		badIDs = [6730]
	
	# these households have bad data for their fridge, which causes errors in the simulation
	if columnID == "refrigerator1":
		badIDs = [7536, 7901, 9019]
	
	# download the household IDs which have some valid data
	query = f'''
		SELECT DISTINCT dataid
		FROM electricity.eg_realpower_1min
		WHERE {columnID} IS NOT NULL
		AND {columnID} > 0.05
		AND localminute >= '{fromDate}'
		AND localminute < '{toDate}'
	'''
	dataIDs = pandas.read_sql_query(query, con=engine)
	validIDs = [id for id in dataIDs["dataid"] if id not in badIDs]
	idFilter = ', '.join(map(str, validIDs))
	
	# download the maximum powers the appliances were drawing for each household
	query = f'''
		SELECT MAX({columnID}) as {columnID}
		FROM electricity.eg_realpower_1min
		WHERE dataid IN ({idFilter})
		AND localminute >= '{fromDate}'
		AND localminute < '{toDate}'
		GROUP BY dataid
	'''
	maxs = pandas.read_sql_query(query, con=engine)
	
	# filter out unreal data (none of these appliances can realistically draw over 20kW)
	maxPowers = maxs[columnID].values
	maxPowers = maxPowers[maxPowers < 20]
	
	# download the average power draw by the appliances for each minute
	query = f'''
		SELECT localminute at time zone 'CST' as localminute, AVG({columnID}) as {columnID}
		FROM electricity.eg_realpower_1min
		WHERE dataid IN ({idFilter})
		AND localminute >= '{fromDate}'
		AND localminute < '{toDate}'
		GROUP BY localminute
		ORDER BY localminute
	'''
	avgs = pandas.read_sql_query(query, con=engine, parse_dates=["localminute"])
	
	# save the downloaded data
	print("Parsing...")
	numpy.savetxt(f"{outFolder}/maxPowers.txt", maxPowers, fmt="%.5f")
	
	# for some appliances there are not many households which have that appliance, so we smooth the data out a bit
	usages = avgs.set_index("localminute").resample('min').interpolate('time').rolling(window=120, center=True, min_periods=1).mean()
	usages.to_csv(f"{outFolder}/averageUsage.csv", index_label="datetime", header=["usage"], float_format="%.5f")
	
	print("Done.")

# dispose of the engine (sometimes the connection keeps hanging otherwise, even after the script has finished)
engine.dispose()

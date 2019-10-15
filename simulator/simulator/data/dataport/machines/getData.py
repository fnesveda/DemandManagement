#!/usr/bin/env python3

import datetime
import os
import sys

from collections import defaultdict
from typing import List, Tuple

import pandas
import sqlalchemy

fromDate = sys.argv[1]
toDate = sys.argv[2]
username = sys.argv[3]
password = sys.argv[4]

# helper function to split an iterable into chunks of a given size
def batch(iterable, n=1):
	l = len(iterable)
	for pos in range(0, l, n):
		yield iterable[pos:min(pos+n, l)]

# create the postgresql connection engine
engine = sqlalchemy.create_engine(f"postgresql://{username}:{password}@dataport.pecanstreet.org:5434/dataport")

# download the data for each appliance type
for columnID, outFolder in [("dishwasher1", "dishwasher"), ("clotheswasher1", "washingmachine")]:
	print(f"Downloading and parsing {outFolder} data...")
	allUsages = []

	# download the household IDs which have some valid data
	query = f'''
		SELECT DISTINCT dataid
		FROM electricity.eg_realpower_1min
		WHERE {columnID} IS NOT NULL
		AND {columnID} > 0.05
		AND localminute >= '{fromDate}'
		AND localminute < '{toDate}'
	'''
	dataIDs = list(pandas.read_sql_query(query, con=engine)["dataid"])
	
	# split the household ids into batches of 10 ids
	# takes a little longer but uses a lot less memory
	idBatches = list(batch(dataIDs, 10))
	for idBatch in batch(dataIDs, 10):
		# download the power draw from the machines for each household in the batch
		idFilter = ', '.join(map(str, idBatch))
		query = f'''
			SELECT dataid, localminute at time zone 'CST' as localminute, {columnID} as machinedemand
			FROM electricity.eg_realpower_1min
			WHERE dataid IN ({idFilter})
			AND localminute >= '{fromDate}'
			AND localminute < '{toDate}'
		'''
		data = pandas.read_sql_query(query, con=engine, parse_dates=["localminute"]).fillna(0)

		# for each machine, identify the intervals it was probably used and generate power profiles from those
		def getUsages(df: pandas.DataFrame) -> List[Tuple[datetime.datetime, List[float]]]:
			machineUsages = []
			startTime = None
			workingProfile = []
			smallValues = 0
			for time, draw in df.sort_values(by="localminute")[["localminute", "machinedemand"]].values:
				# if it's drawing less than 30 watts, then it's possibly done
				if draw <= 0.030:
					# if it's drawing less than 30 watts for more than 5 minutes, then it's probably done
					if smallValues > 5:
						# if it drew some power for more than 20 minutes and less than 4 hours, we call it a valid run and save the profile
						if len(workingProfile) > 20 and len(workingProfile) < 240 and sum(workingProfile) > 1:
							machineUsages.append((startTime, workingProfile[:-smallValues]))
						startTime = None
						workingProfile = []
						smallValues = 0
					# otherwise it was probably a momentary pause in the machine's program, and we continue saving the draw
					else:
						if len(workingProfile) > 0:
							workingProfile.append(draw)
							smallValues += 1
				# otherwise it's still running, we append the current draw to the power profile
				else:
					if startTime is None:
						startTime = pandas.to_datetime(time)
					workingProfile.append(draw)
					smallValues = 0
			
			# if the last item was not zero we do not save the profile, as it may be from an incomplete cycle
			return machineUsages
		
		# get the power usage profiles for each machine
		batchUsages = data.groupby("dataid").apply(getUsages).values
		
		# aggregate the downloaded usages in a list
		for usages in batchUsages:
			allUsages.extend(usages)
	
	# save the power profiles to a file, and calculate the probability that the machine will be turned on at night for each day and save that to a CSV file
	os.makedirs(outFolder, exist_ok=True)
	with open(f"{outFolder}/profiles.txt", "w") as profileFile, open(f"{outFolder}/usages.csv", "w") as usageRatioFile:
		nightRuns = defaultdict(int)
		for start, profile in allUsages:
			profileFile.write(", ".join(["{:.3f}".format(draw) for draw in profile]))
			profileFile.write("\n")
			
			# if it ran between 20:00 and 6:00 then we call it a night run
			date = start.date()
			if start.hour >= 20:
				nightRuns[date] += 1
			if start.hour <= 5:
				nightRuns[date - datetime.timedelta(days=1)] += 1
		
		# save the probability of a night run for each day to a CSV file
		usageRatioFile.write("date,usageRatio\n")
		currentDT = datetime.datetime.strptime(fromDate, "%Y-%m-%d")
		while currentDT < datetime.datetime.strptime(toDate, "%Y-%m-%d"):
			date = currentDT.date()
			ratio = nightRuns[date]/len(allUsages)
			usageRatioFile.write(f"{date},{ratio:.5f}\n")
			currentDT += datetime.timedelta(days=1)
	
	print("Done.")

# dispose of the engine (sometimes the connection keeps hanging otherwise, even after the script has finished)
engine.dispose()

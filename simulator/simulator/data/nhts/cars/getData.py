#!/usr/bin/env python3

import datetime
import os
import sys

from collections import defaultdict
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

import numpy
import pandas
import requests

fromDT = datetime.datetime.strptime(sys.argv[1], "%Y-%m-%d")
toDT = datetime.datetime.strptime(sys.argv[2], "%Y-%m-%d")

# download the NHTS data
print("Downloading NHTS car trip data...")
r = requests.get("https://nhts.ornl.gov/assets/2016/download/Csv.zip")

# unpack it
print("Parsing...")
with ZipFile(BytesIO(r.content)) as archive:
	
	# parse the household data and trip data
	# for each day in the desired interval, get the probability of a car making a trip on that day
	# for each minute in the desired interval write out what ratio of cars is at home
	# for each day in the desired interval write out what trips were the cars taking
	with archive.open("hhpub.csv") as hhpub, archive.open("trippub.csv") as trippub:
		households = pandas.read_csv(hhpub)
		trips = pandas.read_csv(trippub)
		
		# we're only interested in households from Texas
		texans = households[(households["HHSTATE"] == "TX")]
		
		# we're only interested in trips by Texas residents with their personal cars
		texanTrips = trips[(trips["VEHID"] >= 1) & (trips["VEHID"] <= 12) & (trips["HHSTATE"] == "TX")]
		
		# collect information about each of the households
		householdInfo = defaultdict(SimpleNamespace)
		
		# each household is assigned some weight in the data, save that weight
		# each household reports only on one day, save that day
		# also save how many vehicles they have
		for texan in texans.itertuples():
			householdInfo[texan.HOUSEID].weight = texan.WTHHFIN
			householdInfo[texan.HOUSEID].vehicleCount = texan.HHVEHCNT
			householdInfo[texan.HOUSEID].reportMonth = texan.TDAYDATE % 100
			householdInfo[texan.HOUSEID].reportWeekday = (texan.TRAVDAY - 1) % 7
			householdInfo[texan.HOUSEID].usedVehicle = [0, 0, 0, 0]
		
		# for each household save which cars got used on the reported day
		for trip in texanTrips.itertuples():
			if trip.VEHID >= 1 and trip.VEHID <= 4:
				householdInfo[trip.HOUSEID].usedVehicle[trip.VEHID - 1] = 1
		
		# count how many households have how many cars
		weightedCarCountOccurences = [0, 0, 0, 0, 0]
		for household in householdInfo.values():
			weightedCarCountOccurences[min(household.vehicleCount, 4)] += household.weight
		
		carCountProbabilities = [occ / sum(weightedCarCountOccurences) for occ in weightedCarCountOccurences]
		with open("ownershipRatios.csv", "w+") as ownershipRatiosFile:
			ownershipRatiosFile.write("carCount,ratio\n")
			for carCount, ratio in enumerate(carCountProbabilities):
				ownershipRatiosFile.write(f"{carCount},{ratio:.5f}\n")
		
		# count the probability that a car gets used on a given day for each day and each car index
		usages = [defaultdict(lambda: [0, 0]) for _ in range(4)]
		for household in householdInfo.values():
			for car in range(4):
				if household.vehicleCount > car:
					if household.usedVehicle[car] == 1:
						usages[car][(household.reportMonth, household.reportWeekday)][0] += household.weight
					usages[car][(household.reportMonth, household.reportWeekday)][1] += household.weight
	
		# calculate all the statistics for each household car index
		for car in range(4):
			# select the trips by the desired vehicle index
			carTrips = texanTrips[texanTrips["VEHID"] == car + 1]
			
			# for each vehicle and each day determines the first time it left the house and the last time it returned to the house
			def getUsageInterval(df):
				sortedDF = df.sort_values("TDTRPNUM")
				first = sortedDF.iloc[0]
				last = sortedDF.iloc[-1]
				# we're interested only in the days where the first trip started from home and last trip ended at home
				if (first["WHYFROM"] in [1, 2]) and (last["WHYTO"] in [1, 2]) and (first["STRTTIME"] < last["ENDTIME"]):
					year = first["TDAYDATE"] // 100
					month = first["TDAYDATE"] % 100
					# Americans have Sunday as the first day of the week, fix that
					weekday = first["TRAVDAY"] - 1 % 7
					departure = "{:02d}:{:02d}".format(first["STRTTIME"] // 100, first["STRTTIME"] % 100)
					arrival = "{:02d}:{:02d}".format(last["ENDTIME"] // 100, last["ENDTIME"] % 100)
					return (year, month, weekday, departure, arrival)
				else:
					return None
			
			# group the trips by household and get the usage intervals of the desired vehicle
			times = carTrips.groupby(["HOUSEID"]).apply(getUsageInterval).values
			
			# filter out reports where nothing happened
			times = list(times[times != None])
			daytrips = pandas.DataFrame(times, columns=["Year", "Month", "Weekday", "Departure", "Arrival"])
			
			# convert data to dictionary
			dateGroups = daytrips.groupby(["Month", "Weekday"])[["Departure", "Arrival"]]
			intervals = dateGroups.apply(lambda group: list(group.itertuples(index=False, name=None))).to_dict()
			
			# create the folder for saving the data
			outFolder = f"car{car+1}"
			os.makedirs(outFolder, exist_ok=True)
			
			# write the parsed data out to files
			# for each minute in the desired interval write out what ratio of cars is at home
			# for each day in the desired interval write out what trips were the cars taking
			with open(f"{outFolder}/usageRatios.csv", "w+") as usageRatioFile, open(f"{outFolder}/trips.txt", "w+") as tripsFile, open(f"{outFolder}/availability.csv", "w+") as availabilityFile:
				# write headers
				usageRatioFile.write("date,usageRatio\n")
				availabilityFile.write("datetime,availability\n")

				currentDT = fromDT
				while currentDT < toDT:
					usage = usages[car][(currentDT.month, currentDT.weekday())]
					usageRatio = usage[0] / max(1, usage[1])
					usageRatioFile.write(f"{currentDT.date()},{usageRatio:.5f}\n")

					trips = intervals.get((currentDT.month, currentDT.weekday()), [])
					atHome = numpy.full(24*60, fill_value=max(len(trips), 1), dtype=float)
					
					for dep, arr in trips:
						departureSlot = 60 * int(dep[:2]) + int(dep[-2:])
						arrivalSlot = 60 * int(arr[:2]) + int(arr[-2:])
						atHome[departureSlot:arrivalSlot] -= 1
					
					availabilityForDay = 1 - (usageRatio * (1 - (atHome / max(len(trips), 1))))
					for minute, availability in enumerate(availabilityForDay):
						availabilityFile.write(f"{currentDT+datetime.timedelta(minutes=minute)},{availability:.5f}\n")
					
					tripsFile.write(f"{currentDT.date()}: [")
					tripsFile.write(", ".join([f"{dep}-{arr}" for dep, arr in trips]))
					tripsFile.write("]\n")
					
					currentDT += datetime.timedelta(days=1)

print("NHTS car trip data retrieved.")

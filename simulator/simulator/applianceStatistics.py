#!/usr/bin/env python3

import datetime
import json
import math
import random
import os

from abc import ABC
from collections import defaultdict
from types import SimpleNamespace
from typing import Dict, List, Tuple

import numpy
import pandas

from .constants import oneDay
from .profile import Profile
from .utils import minutesIn

thisDir = os.path.dirname(__file__)

# base class for household appliance statistics
# contains parameters based on which random appliances and their random usages will be generated
class ApplianceStatistics(ABC):
	pass

# statistics of battery-based household appliances (e.g. electric car)
class BatteryStatistics(ApplianceStatistics):
	# possible charging powers of the appliance type
	chargingPowers: List[float]
	# probabilities that the appliance will get used on a given day
	usageProbabilities: Dict[datetime.date, float]
	# possible charges which the appliance might need after usage on a given day
	neededCharges: Dict[datetime.date, List[float]]
	# average charge needed by the appliance type on a given day
	averageNeededCharge: Dict[datetime.date, float]
	# intervals in which the appliance might be used on a given day
	usageIntervals: Dict[datetime.date, List[Tuple[datetime.time, datetime.time]]]
	# profile of what ratio of appliances are available for charging at any given date and time
	availabilityProfile: Profile
	
	# generates a random charging power for the appliance
	def randomChargingPower(self) -> float:
		return random.choice(self.chargingPowers)
	
	# generates a random needed charge for the appliance, if the appliance gets used at all
	def randomNeededCharge(self, date: datetime.date) -> float:
		if random.random() < self.usageProbabilities[date]:
			return random.choice(self.neededCharges[date])
		else:
			return 0.0
	
	# generates a random usage interval for the appliance
	def randomUsageInterval(self, date: datetime.date) -> Tuple[datetime.time, datetime.time]:
		if len(self.usageIntervals[date]) == 0:
			return (None, None)
		else:
			return random.choice(self.usageIntervals[date])
	
	# loads charging powers from a file
	# the file should have one possible charging power on each line
	def loadChargingPowersFromFile(self, path):
		self.chargingPowers = list(numpy.loadtxt(path))
	
	# loads the usage probabilities from a CSV file
	# in each row in the file there should be a date in the first column and the corresponding usage probability in the second column
	def loadUsageProbabilitiesFromFile(self, path):
		data = pandas.read_csv(path, parse_dates=[0])
		self.usageProbabilities = {}
		for timestamp, usageprob in data.itertuples(index=False, name=None):
			date = timestamp.date()
			self.usageProbabilities[date] = usageprob
	
	# loads needed charges from a file
	# on each line of the file there should be a date followed by a list of possible needed charges on that date
	def loadNeededChargesFromFile(self, path):
		self.neededCharges = {}
		self.averageNeededCharge = {}
		with open(path, "r") as chargesFile:
			for line in chargesFile:
				date = datetime.datetime.strptime(line.strip()[:10], "%Y-%m-%d").date()
				charges = [float(x) for x in line.strip()[11:].strip(" []\n").split(",")]
				self.neededCharges[date] = charges
				self.averageNeededCharge[date] = numpy.mean(charges) * self.usageProbabilities[date]
	
	# loads the usage intervals from a file
	# on each line of the file there should be a date followed by a list of possible usage intervals on that date
	def loadUsageIntervalsFromFile(self, path):
		def parseInterval(interval) -> Tuple[datetime.time, datetime.time]:
			if len(interval) < 10:
				return (None, None)
			else:
				start = datetime.datetime.strptime(interval[:5], "%H:%M").time()
				end = datetime.datetime.strptime(interval[-5:], "%H:%M").time()
				return (start, end)
		
		self.usageIntervals = defaultdict(list)
		with open(path, "r") as usageIntervalsFile:
			for line in usageIntervalsFile:
				date = datetime.datetime.strptime(line.strip()[:10], "%Y-%m-%d").date()
				intervals = list(map(parseInterval, line.strip()[11:].strip(" []\n").split(", ")))
				self.usageIntervals[date].extend(intervals)
	
	# loads the availability profile from a CSV file
	# in each row in the file there should be a date and time in the first column and the corresponding appliance availability in the second column
	def loadAvailabilityProfileFromFile(self, path):
		self.availabilityProfile = Profile.fromCSV(path)

# statistics of accumulator-based household appliances (e.g. water heater, refrigerator)
class AccumulatorStatistics(ApplianceStatistics):
	# list of possible charging powers for the appliance type
	chargingPowers: List[float]
	# average charging power of the appliance type
	averageChargingPower: float
	# mean appliance capacity and its standard deviation
	capacityParameters: Tuple[float, float]
	# the average discharging profile for the appliance type
	dischargingProfile: Profile
	# average needed charge for the appliance type for each day
	averageDailyCharge: Dict[datetime.date, float]
	# mean and standard deviation of the scale of discharging profiles of the appliance type
	dischargingProfileScaleParameters: Tuple[float, float]
	
	# generates a random charging power for the appliance
	def randomChargingPower(self) -> float:
		return random.choice(self.chargingPowers)
	
	# generates a random capacity power for the appliance
	def randomCapacity(self) -> float:
		return random.gauss(*self.capacityParameters)
	
	# generates a random discharging profile scale
	def randomDischargingProfileScale(self) -> float:
		return random.gauss(*self.dischargingProfileScaleParameters)
	
	# loads charging powers from a file
	# the file should have one possible charging power on each line
	def loadChargingPowersFromFile(self, path: str):
		self.chargingPowers = list(numpy.loadtxt(path))
		self.averageChargingPower = numpy.mean(self.chargingPowers)
	
	# loads the average discharging profile from a CSV file
	# in each row in the file there should be a date and time in the first column and the corresponding average discharging power in the second column
	def loadDischargingProfileFromFile(self, path: str):
		self.dischargingProfile = Profile.fromCSV(path)
		self.averageDailyCharge = {d: s * 24 for (d, s) in self.dischargingProfile.dailyAverages().items()}

# statistics for machine-like household appliances (e.g. dishwasher, washing machine)
class MachineStatistics(ApplianceStatistics):
	# mean minute of the day that the machine can start after, and its standard deviation
	startAfterParameters: Tuple[int, int]
	# mean minute of the day that the machine must finish by, and its standard deviation
	finishByParameters: Tuple[int, int]
	# probabilities that the machine will get used on a given day
	usageProbabilities: Dict[datetime.date, float]
	# possible power usage profiles of the machine type
	usageProfiles: List[numpy.ndarray]
	# average power needed by the machine type on a given day
	averagePowerNeeded: Dict[datetime.date, float]
	
	# generates a random starting time
	def randomStartAfter(self) -> datetime.time:
		minutes = min(max(0, math.floor(random.gauss(*self.startAfterParameters))), minutesIn(oneDay)-1)
		return datetime.time(minutes // 60, minutes % 60)
	
	# generates a random finishing time
	def randomFinishBy(self) -> datetime.time:
		minutes = min(max(0, math.floor(random.gauss(*self.finishByParameters))), minutesIn(oneDay)-1)
		return datetime.time(minutes // 60, minutes % 60)
	
	# picks a random choosing profile of all the possible profiles
	def randomUsageProfile(self) -> numpy.ndarray:
		return random.choice(self.usageProfiles)
	
	# loads the usage probabilities from a CSV file
	# in each row in the file there should be a date in the first column and the corresponding usage probability in the second column
	def loadUsageProbabilitiesFromFile(self, path: str):
		data = pandas.read_csv(path, parse_dates=[0])
		self.usageProbabilities = {}
		for timestamp, usageprob in data.itertuples(index=False, name=None):
			date = timestamp.date()
			self.usageProbabilities[date] = usageprob
	
	# loads the power usage profiles from a file
	# on each line of the file there should be a list of power draws for each minute of the operation of the machine
	def loadUsageProfilesFromFile(self, path: str):
		self.usageProfiles = []
		sums = []
		with open(path, "r") as sourceFile:
			for line in sourceFile:
				profile = numpy.fromstring(line, dtype=float, sep=",")
				self.usageProfiles.append(profile)
				sums.append(numpy.sum(profile)/60)
		
		averagePowerNeeded = numpy.mean(sums)
		
		self.averagePowerNeeded = {}
		for date, usageProbability in self.usageProbabilities.items():
			self.averagePowerNeeded[date] = averagePowerNeeded * usageProbability

# ownership ratios of various household appliances and vehicles
# adapted from https://www.eia.gov/consumption/residential/reports/2009/state_briefs/pdf/tx.pdf
with open(f"{thisDir}/data/manual/ownershipRatios.json", "r") as ownershipRatiosFile:
	ownershipRatios = SimpleNamespace(**json.load(ownershipRatiosFile))

# probabilities that a house owns some number of cars
carCountProbabilities = list(pandas.read_csv(f"{thisDir}/data/nhts/cars/ownershipRatios.csv")["ratio"])
atLeastThisManyCarsProbability = [sum(carCountProbabilities[i:]) for i in range(len(carCountProbabilities))]

# electric car statistics
# each car in a household get used differently
carStatistics = []
for car in range(4):
	carStatistics.append(BatteryStatistics())
	carStatistics[car].loadUsageProbabilitiesFromFile(f"{thisDir}/data/nhts/cars/car{car+1}/usageRatios.csv")
	carStatistics[car].loadUsageIntervalsFromFile(f"{thisDir}/data/nhts/cars/car{car+1}/trips.txt")
	carStatistics[car].loadAvailabilityProfileFromFile(f"{thisDir}/data/nhts/cars/car{car+1}/availability.csv")
	carStatistics[car].loadNeededChargesFromFile(f"{thisDir}/data/dataport/cars/charges.txt")
	carStatistics[car].loadChargingPowersFromFile(f"{thisDir}/data/dataport/cars/maxPowers.txt")

# load the accumulator capacities statistics from a json file
with open(f"{thisDir}/data/manual/applianceCapacities.json", "r") as capacitiesFile:
	capacities = json.load(capacitiesFile, object_hook=lambda dct: SimpleNamespace(**dct))

# air conditioning statistics
airConditioningStatistics = AccumulatorStatistics()
airConditioningStatistics.capacityParameters = (capacities.airConditioning.mean, capacities.airConditioning.std)
airConditioningStatistics.dischargingProfileScaleParameters = (1, 0.3)
airConditioningStatistics.loadChargingPowersFromFile(f"{thisDir}/data/dataport/accumulators/airconditioning/maxPowers.txt")
airConditioningStatistics.loadDischargingProfileFromFile(f"{thisDir}/data/dataport/accumulators/airconditioning/averageUsage.csv")

# electrical heating statistics
electricalHeatingStatistics = AccumulatorStatistics()
electricalHeatingStatistics.capacityParameters = (capacities.electricalHeating.mean, capacities.electricalHeating.std)
electricalHeatingStatistics.dischargingProfileScaleParameters = (1, 0.3)
electricalHeatingStatistics.loadChargingPowersFromFile(f"{thisDir}/data/dataport/accumulators/electricalheating/maxPowers.txt")
electricalHeatingStatistics.loadDischargingProfileFromFile(f"{thisDir}/data/dataport/accumulators/electricalheating/averageUsage.csv")

# refrigerator statistics
fridgeStatistics = AccumulatorStatistics()
fridgeStatistics.capacityParameters = (capacities.fridge.mean, capacities.fridge.std)
fridgeStatistics.dischargingProfileScaleParameters = (1, 0.3)
fridgeStatistics.loadChargingPowersFromFile(f"{thisDir}/data/dataport/accumulators/fridge/maxPowers.txt")
fridgeStatistics.loadDischargingProfileFromFile(f"{thisDir}/data/dataport/accumulators/fridge/averageUsage.csv")

# water heater statistics
waterHeaterStatistics = AccumulatorStatistics()
waterHeaterStatistics.capacityParameters = (capacities.waterHeater.mean, capacities.waterHeater.std)
waterHeaterStatistics.dischargingProfileScaleParameters = (1, 0.3)
waterHeaterStatistics.loadChargingPowersFromFile(f"{thisDir}/data/dataport/accumulators/waterheater/maxPowers.txt")
waterHeaterStatistics.loadDischargingProfileFromFile(f"{thisDir}/data/dataport/accumulators/waterheater/averageUsage.csv")

# dishwasher statistics
dishwasherStatistics = MachineStatistics()
dishwasherStatistics.startAfterParameters = (21*60, 60)
dishwasherStatistics.finishByParameters = (5*60, 60)
dishwasherStatistics.loadUsageProbabilitiesFromFile(f"{thisDir}/data/dataport/machines/dishwasher/usages.csv")
dishwasherStatistics.loadUsageProfilesFromFile(f"{thisDir}/data/dataport/machines/dishwasher/profiles.txt")

# washing machine statistics
washingMachineStatistics = MachineStatistics()
washingMachineStatistics.startAfterParameters = (21*60, 60)
washingMachineStatistics.finishByParameters = (5*60, 60)
washingMachineStatistics.loadUsageProbabilitiesFromFile(f"{thisDir}/data/dataport/machines/washingmachine/usages.csv")
washingMachineStatistics.loadUsageProfilesFromFile(f"{thisDir}/data/dataport/machines/washingmachine/profiles.txt")

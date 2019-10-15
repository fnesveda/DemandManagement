#!/usr/bin/env python3

import datetime
import math
import random

from abc import ABC, abstractmethod, abstractclassmethod
from types import SimpleNamespace

import numpy

from . import applianceStatistics
from . import utils

from .constants import oneDay
from .profile import Profile
from .utils import minutesIn

# abstract base class for household appliances
class Appliance(ABC):
	# current date and time in the simulation
	currentDT: datetime.datetime
	# an object for storing information between demand calculations
	memory: SimpleNamespace
	# appliance usage statistics
	usageStatistics: applianceStatistics.ApplianceStatistics
	# the electricity price for any given minute in the simulation
	priceProfile: Profile
	# the electricity demand of this appliance if it was smart
	smartDemand: Profile
	# the electricity demand of this appliance if it would charge as early as possible
	uncontrolledDemand: Profile
	# the electricity demand of this appliance if it would charge evenly over their use period
	spreadOutDemand: Profile
	
	# constructor, just prepares the variables
	def __init__(self):
		self.memory = SimpleNamespace()
		self.priceProfile = Profile()
		self.smartDemand = Profile()
		self.uncontrolledDemand = Profile()
		self.spreadOutDemand = Profile()
	
	# creates a random appliance with the right parameters
	@abstractclassmethod
	def random(cls):
		pass
	
	# sets up the appliance for the simulation
	def setUp(self, dt: datetime.datetime):
		self.currentDT = dt
		# generate usage for one day in the future
		self.generateUsage(dt, dt + oneDay)
	
	# moves ahead one day and does all the calculations that need to be done in that day
	def tick(self):
		# remove past, unneeded values from the profiles to free up some memory
		self.priceProfile.prune(self.currentDT - oneDay)
		self.smartDemand.prune(self.currentDT - oneDay)
		self.uncontrolledDemand.prune(self.currentDT - oneDay)
		self.spreadOutDemand.prune(self.currentDT - oneDay)
		
		# generate appliance usage for one more day in the future
		self.generateUsage(self.currentDT + oneDay, self.currentDT + 2 * oneDay)
		# calculate the power demand for the next day
		self.calculateDemand(self.currentDT, self.currentDT + oneDay)
		
		# move ahead one day
		self.currentDT += oneDay
	
	# generates appliance usage for a given time interval
	@abstractmethod
	def generateUsage(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		pass
	
	# calculates appliance power demand for a given time interval
	def calculateDemand(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		self.calculateSmartDemand(fromDT, toDT)
		self.calculateUncontrolledDemand(fromDT, toDT)
		self.calculateSpreadOutDemand(fromDT, toDT)
	
	# calculates appliance power demand for a given time interval acting as if the appliance was smart
	@abstractmethod
	def calculateSmartDemand(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		pass
	
	# calculates appliance power demand for a given time interval acting as if if it would charge as early as possible
	@abstractmethod
	def calculateUncontrolledDemand(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		pass
	
	# calculates appliance power demand for a given time interval acting as if if it would charge evenly over the use period
	@abstractmethod
	def calculateSpreadOutDemand(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		pass
	
	# sets the electricity price profile for a given time interval
	def setPriceProfile(self, dt: datetime.datetime, prices: numpy.ndarray):
		self.priceProfile.set(dt, prices)

# abstract base class for battery-based household appliances (e.g. electric car)
class Battery(Appliance, ABC):
	# appliance usage statistics
	usageStatistics: applianceStatistics.BatteryStatistics
	
	# the power with which the battery charges
	chargingPower: float # kW
	
	# constructor, just prepares the variables
	def __init__(self, chargingPower: float = 0):
		self.chargingPower = chargingPower
		super().__init__()
		# for each day keeps disconnection time, connection time and charge needed after the usage
		self.memory.usages = dict()
	
	# creates a random appliance with the right parameters
	@classmethod
	def random(cls):
		chargingPower = cls.usageStatistics.randomChargingPower()
		return cls(chargingPower=chargingPower)
	
	# generates appliance usage for a given time interval
	def generateUsage(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		# we need to know the usage for one day ahead (at least the disconnect time)
		for midnight in utils.midnightsBetween(fromDT, toDT+oneDay):
			date = midnight.date()
			if date not in self.memory.usages:
				disconnectionTime, connectionTime = self.usageStatistics.randomUsageInterval(date)
				# if the values are invalid make up an usage interval giving us as much charging time as possible
				if disconnectionTime is None:
					disconnectionTime = datetime.time(23, 59)
				if connectionTime is None:
					connectionTime = datetime.time(00, 00)
					
				chargeNeeded = self.usageStatistics.randomNeededCharge(date)
				self.memory.usages[date] = ((disconnectionTime, connectionTime), chargeNeeded)
	
	# calculates appliance power demand for a given time interval acting as if the appliance was smart
	def calculateSmartDemand(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		# for each day in the interval, it charges the battery in the minutes with the cheapest electricity available
		for midnight in utils.midnightsBetween(fromDT, toDT):
			date = midnight.date()
			powerProfile = numpy.zeros(2*minutesIn(oneDay), dtype=float)
			
			# get the needed charge and the interval when the battery is connected
			((_, connectionTime), chargeNeeded) = self.memory.usages[date]
			((disconnectionTime, _), _) = self.memory.usages[date + oneDay]
			
			# get for how long the battery must be charged
			chargePerSlot = self.chargingPower / 60 # kWh per minute
			slotsToChargeCompletely = math.ceil(chargeNeeded / chargePerSlot)
			
			# if it needs to be charged, charge it
			if slotsToChargeCompletely > 0:
				connectionSlot = connectionTime.hour * 60 + connectionTime.minute
				disconnectionSlot = minutesIn(oneDay) + disconnectionTime.hour * 60 + disconnectionTime.minute
				
				# if there is not enough time to charge the battery completely, just charge it all the available time
				if disconnectionSlot - connectionSlot <= slotsToChargeCompletely:
					powerProfile[connectionSlot:disconnectionSlot] = self.chargingPower
				# otherwise pick enough of the cheapest time slots and charge the battery during those
				else:
					priceProfile = self.priceProfile.get(midnight, midnight+2*oneDay)
					cheapestSlots = numpy.argpartition(priceProfile[connectionSlot:disconnectionSlot], slotsToChargeCompletely)[:slotsToChargeCompletely] + connectionSlot
					powerProfile[cheapestSlots[:-1]] = self.chargingPower
					lastSlotCharge = chargeNeeded - (chargePerSlot * (slotsToChargeCompletely - 1))
					powerProfile[cheapestSlots[-1]] = lastSlotCharge * 60
			
			self.smartDemand.add(midnight, powerProfile)
	
	# calculates appliance power demand for a given time interval acting as if the battery wanted to charge as early as possible
	def calculateUncontrolledDemand(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		# for each day in the interval, the appliance starts charging the battery as soon as it is connected to power
		for midnight in utils.midnightsBetween(fromDT, toDT):
			date = midnight.date()
			
			powerProfile = numpy.zeros(2*minutesIn(oneDay), dtype=float)
			
			# get the needed charge and the interval when the battery is connected
			((_, connectionTime), chargeNeeded) = self.memory.usages[date]
			((disconnectionTime, _), _) = self.memory.usages[date + oneDay]
			
			# get for how long the battery must be charged
			chargePerSlot = self.chargingPower / 60
			slotsToChargeCompletely = math.ceil(chargeNeeded / chargePerSlot)
			
			# if it needs to be charged, charge it
			if slotsToChargeCompletely > 0:
				connectionSlot = connectionTime.hour * 60 + connectionTime.minute
				disconnectionSlot = minutesIn(oneDay) + disconnectionTime.hour * 60 + disconnectionTime.minute
				
				# if there is not enough time to charge the battery completely, just charge it all the available time
				if disconnectionSlot - connectionSlot < slotsToChargeCompletely:
					powerProfile[connectionSlot:disconnectionSlot] = self.chargingPower
				# otherwise start charging it as soon as it is available and charge until it's full
				else:
					powerProfile[connectionSlot:connectionSlot+slotsToChargeCompletely-1] = self.chargingPower
					lastSlotCharge = chargeNeeded - (chargePerSlot * (slotsToChargeCompletely - 1))
					powerProfile[connectionSlot+slotsToChargeCompletely] = lastSlotCharge * 60
			
			self.uncontrolledDemand.add(midnight, powerProfile)
	
	# calculates appliance power demand for a given time interval acting as if the battery wanted to charge as evenly as possible
	def calculateSpreadOutDemand(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		# for each day in the interval, the appliance starts charging the battery as soon as it is connected to power
		for midnight in utils.midnightsBetween(fromDT, toDT):
			date = midnight.date()
			
			powerProfile = numpy.zeros(2*minutesIn(oneDay), dtype=float)
			
			# get the needed charge and the interval when the battery is connected
			((_, connectionTime), chargeNeeded) = self.memory.usages[date]
			((disconnectionTime, _), _) = self.memory.usages[date + oneDay]
			
			# get for how long the battery must be charged
			chargePerSlot = self.chargingPower / 60
			slotsToChargeCompletely = math.ceil(chargeNeeded / chargePerSlot)
			
			# if it needs to be charged, charge it
			if slotsToChargeCompletely > 0:
				connectionSlot = connectionTime.hour * 60 + connectionTime.minute
				disconnectionSlot = minutesIn(oneDay) + disconnectionTime.hour * 60 + disconnectionTime.minute
				
				# if there is not enough time to charge the battery completely, just charge it all the available time
				if disconnectionSlot - connectionSlot < slotsToChargeCompletely:
					powerProfile[connectionSlot:disconnectionSlot] = self.chargingPower
				# otherwise charge it evenly over the whole connected period
				else:
					powerProfile[connectionSlot:disconnectionSlot] = chargeNeeded / ((disconnectionSlot - connectionSlot) / 60)
			
			self.spreadOutDemand.add(midnight, powerProfile)

# abstract base class for accumulator-based household appliances (e.g. water heater, refrigerator)
class Accumulator(Appliance, ABC):
	# appliance usage statistics
	usageStatistics: applianceStatistics.AccumulatorStatistics
	# the power with which the appliance charges
	chargingPower: float # kW
	# the charging capacity of the appliance
	capacity: float # kWh
	
	# constructor, just prepares the variables
	def __init__(self, chargingPower: float, capacity: float, dischargingProfileScale: float):
		super().__init__()
		self.chargingPower = chargingPower
		self.capacity = capacity
		
		# variables for storing the state of the appliance between calculations
		self.memory.dischargingProfileScale = dischargingProfileScale
		self.memory.smart = SimpleNamespace()
		self.memory.smart.currentCharge = random.random() * self.capacity
		self.memory.uncontrolled = SimpleNamespace()
		self.memory.uncontrolled.currentCharge = self.capacity
		self.memory.spreadOut = SimpleNamespace()
		self.memory.spreadOut.charging = random.choice([True, False])
		self.memory.spreadOut.currentCharge = random.random() * self.capacity

		# the profile of how the accumulator discharges (e.g. water heater cools down or gets used, fridge heats up)
		self.memory.dischargingProfile = Profile()
	
	# creates a random accumulator with the right parameters
	@classmethod
	def random(cls):
		chargingPower = cls.usageStatistics.randomChargingPower()
		# in this simulator we can't have an appliance which would charge up faster than in one minute
		capacity = max(cls.usageStatistics.randomCapacity(), (1.1*chargingPower/60))
		# stronger appliances are usually those which get used more, so scale the random discharging profile by the charging power of the appliance
		dischargingProfileScale = cls.usageStatistics.randomDischargingProfileScale() * (chargingPower / cls.usageStatistics.averageChargingPower)
		return cls(chargingPower, capacity, dischargingProfileScale)
	
	# moves ahead one day and does all the calculations that need to be done in that day
	def tick(self):
		# remove past, unneeded values from the profiles to free up some memory
		self.memory.dischargingProfile.prune(self.currentDT - oneDay)
		super().tick()
	
	# generates appliance usage for a given time interval
	def generateUsage(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		# generate how much will the accumulator discharge during that interval
		dischargingProfile = self.usageStatistics.dischargingProfile.get(fromDT, toDT) * self.memory.dischargingProfileScale
		self.memory.dischargingProfile.set(fromDT, dischargingProfile)
	
	# calculates appliance power demand for a given time interval acting as if the appliance was smart
	def calculateSmartDemand(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		# adapted from https://ktiml.mff.cuni.cz/~fink/publication/greedy.pdf
		# asymptotically, this would be faster with prefix sum trees or union-find data structures
		# but in Python that is actually spreadOuter than using a quadratic algorithm with numpy
		# the limit preparation, which is linear, is spreadOuter than the actual algorithm anyway, so it doesn't matter
		
		# get the cheapest slots in which to turn on the appliance so that it never discharges under its lower limit and never charges over its upper limit
		# normally, the appliance doesn't charge more than it needs to, so at the end of the interval it would be charged barely above the lower limit
		# then at the start of the next calculated interval it would need to charge more to catch up
		# we calculate the charging profile with a bit of an overlap to avoid this
		endMargin = oneDay
		wantedSlots = utils.minutesBetween(fromDT, toDT)
		totalSlots = utils.minutesBetween(fromDT, toDT+endMargin)
		
		# the electricity prices in the interval
		priceProfile = self.priceProfile.get(fromDT, toDT+endMargin)
		
		# how much energy goes into the appliance each minute it's turned on
		chargingRate = self.chargingPower / 60 # kWh per minute
		# how much energy leaves the appliance each minute of the interval
		dischargingRates = self.memory.dischargingProfile.get(fromDT, toDT+endMargin) / 60 # kWh per minute for each minute
		
		startingCharge = self.memory.smart.currentCharge # kWh
		
		# never discharge past 0 and never charge over the capacity
		lowerTarget = 0 # kWh
		upperTarget = self.capacity # kWh
		
		# convert the limits and charging rates to integer steps
		dischargingSum = numpy.cumsum(dischargingRates) # total kWh cumulatively discharged for each minute
		lowerLimit = numpy.ceil((lowerTarget - startingCharge + dischargingSum) / chargingRate).astype(int)
		upperLimit = numpy.floor((upperTarget - startingCharge + dischargingSum) / chargingRate).astype(int)
		lowerLimit = numpy.maximum(lowerLimit, 0)
		upperLimit = numpy.minimum(upperLimit, totalSlots)
		
		# cut the limits to all the reachable charge values
		for i in range(totalSlots - 1):
			if lowerLimit[i+1] < lowerLimit[i]:
				lowerLimit[i+1] = lowerLimit[i]
			if upperLimit[i+1] < upperLimit[i]:
				upperLimit[i+1] = upperLimit[i]
		
		for i in reversed(range(totalSlots - 1)):
			if lowerLimit[i] < lowerLimit[i+1] - 1:
				lowerLimit[i] = lowerLimit[i+1] - 1
			if upperLimit[i] < upperLimit[i+1] - 1:
				upperLimit[i] = upperLimit[i+1] - 1
		
		for i in range(totalSlots):
			if lowerLimit[i] > i:
				lowerLimit[i] = i
			else:
				break
		
		for i in range(totalSlots):
			if upperLimit[i] > i + 1:
				upperLimit[i] = i + 1
			else:
				break
		
		# the profile of how the appliance will charge, 1 for every slot it will charge, 0 otherwise
		chargingProfile = numpy.zeros(totalSlots)
		
		# starting point of the algorithm is 0
		lowerLimit = numpy.concatenate(([0], lowerLimit))
		upperLimit = numpy.concatenate(([0], upperLimit))
		
		# the charging slots ordered from cheapest slot to most expensive slot
		cheapestOrder = numpy.argsort(priceProfile)
		for slot in cheapestOrder:
			# if the appliance can be turned on at that slot, turn it on and update the limits
			if lowerLimit[slot] < upperLimit[slot+1] and lowerLimit[slot] < lowerLimit[-1]:
				chargingProfile[slot] = 1
				# update the limits to what's newly possible now
				lowerSlot = (lowerLimit > lowerLimit[slot]).argmax()
				upperSlot = (upperLimit == upperLimit[slot+1]).argmax()
				lowerLimit[lowerSlot:] -= 1
				upperLimit[upperSlot:] -= 1
		
		# save the new charge level for the appliance
		self.memory.smart.currentCharge = startingCharge - dischargingSum[wantedSlots-1] + numpy.sum(chargingProfile[:wantedSlots]) * chargingRate
		
		# get the power profile for the charging interval and save it
		powerProfile = chargingProfile[:wantedSlots] * self.chargingPower
		self.smartDemand.set(fromDT, powerProfile)
	
	# calculates appliance power demand for a given time interval acting as if the accumulator wanted to stay as charged as possible
	def calculateUncontrolledDemand(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		# simulates an uncontrolled charging algorithm, when an appliance wants to have as much energy stored as possible
		
		# how much energy goes into the appliance each minute it's turned on
		chargingRate = self.chargingPower / 60 # kWh per minute
		# how much energy leaves the appliance each minute of the interval
		dischargingRates = self.memory.dischargingProfile.get(fromDT, toDT) / 60 # kWh per minute for each minute
		
		# never discharge past 0 and never charge over the capacity
		upperLimit = self.capacity # kWh
		
		# get the current charge from memory
		charge = self.memory.uncontrolled.currentCharge
		
		# the power profile for the interval
		totalSlots = utils.minutesBetween(fromDT, toDT)
		powerProfile = numpy.zeros(totalSlots)
		
		# simulate the progression of charge during the interval
		for slot in range(totalSlots):
			charge -= dischargingRates[slot]
			if charge + chargingRate < upperLimit:
				charge += chargingRate
				powerProfile[slot] = self.chargingPower
		
		# save the new charge level to memory
		self.memory.uncontrolled.currentCharge = charge
		
		# save the calculated demand
		self.uncontrolledDemand.set(fromDT, powerProfile)
	
	# calculates appliance power demand for a given time interval acting as if the accumulator wanted to always charge completely and then discharge completely
	def calculateSpreadOutDemand(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		# simulates a thermostat-based charging, when an appliance starts charging when it discharges past some threshhold, and stops charging when it's fully charged
		
		# how much energy goes into the appliance each minute it's turned on
		chargingRate = self.chargingPower / 60 # kWh per minute
		# how much energy leaves the appliance each minute of the interval
		dischargingRates = self.memory.dischargingProfile.get(fromDT, toDT) / 60 # kWh per minute for each minute
		
		# never discharge past 0 and never charge over the capacity
		lowerLimit = 0 # kWh
		upperLimit = self.capacity # kWh
		
		# get the current charge from memory
		charge = self.memory.spreadOut.currentCharge
		# get if we're charging right now from memory
		charging = self.memory.spreadOut.charging
		
		# the power profile for the interval
		totalSlots = utils.minutesBetween(fromDT, toDT)
		powerProfile = numpy.zeros(totalSlots)
		# simulate the progression of charge during the interval
		for slot in range(totalSlots):
			charge -= dischargingRates[slot]
			if charging:
				if charge + chargingRate > upperLimit:
					charging = False
			else:
				if charge <= lowerLimit:
					charging = True
			
			if charging:
				charge += chargingRate
				powerProfile[slot] = self.chargingPower
		
		# save the new charge level and if it was charging and the end of the interval
		self.memory.spreadOut.currentCharge = charge
		self.memory.spreadOut.charging = charging
		
		# save the calculated demand
		self.spreadOutDemand.set(fromDT, powerProfile)

# abstract base class for machine-like household appliances (e.g. dishwasher, washing machine)
class Machine(Appliance, ABC):
	# appliance usage statistics
	usageStatistics: applianceStatistics.MachineStatistics
	
	# constructor, just prepares the variables
	def __init__(self):
		super().__init__()
		# for each day keeps time the appliance should start after, time it should finish by and the usage profile of that run of the appliance
		self.memory.usages = dict()
	
	# creates a random appliance with the right parameters
	@classmethod
	def random(cls):
		return cls()
	
	# generates appliance usage for a given interval
	def generateUsage(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		# for each day decide if the appliance will be used at all,
		# and if so, generate the time the appliance should start after, time it should finish by
		# and the usage profile of that run of the appliance
		for midnight in utils.midnightsBetween(fromDT, toDT):
			date = midnight.date()
			if date not in self.memory.usages:
				if random.random() < self.usageStatistics.usageProbabilities[date]:
					startAfter = self.usageStatistics.randomStartAfter()
					finishBy = self.usageStatistics.randomFinishBy()
					powerUsageProfile = self.usageStatistics.randomUsageProfile()
					self.memory.usages[date] = ((startAfter, finishBy), powerUsageProfile)
				else:
					self.memory.usages[date] = None
	
	# calculates appliance power demand for a given time interval acting as if the appliance was NOT smart
	def calculateSmartDemand(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		# for each day in the interval, calculate the best time to start the appliance so that the run would be the cheapest
		for midnight in utils.midnightsBetween(fromDT, toDT):
			date = midnight.date()
			# the power profile of that day (plus some overlap)
			powerProfile = numpy.zeros(2 * utils.minutesIn(oneDay))
			
			# get the appliance usage for that day and act accordingly
			usage = self.memory.usages[date]
			if usage is not None:
				# the price for the interval
				priceProfile = self.priceProfile.get(midnight, midnight+2*oneDay)
				
				# the slots in which the appliance is available for being turned on
				((startAfter, finishBy), powerUsageProfile) = usage
				startAfterSlot = startAfter.hour * 60 + startAfter.minute
				finishBySlot = finishBy.hour * 60 + finishBy.minute + utils.minutesIn(oneDay)
				
				# the length of the run of the appliance
				runtime = powerUsageProfile.size
				cheapestSlot = startAfterSlot
				
				# if there is enough time to run the appliance, find the time to start at so that the run would be the cheapest
				if finishBySlot - startAfterSlot > runtime:
					# basically we have to try all the times between the starting and finishing slots to find the cheapest one
					cheapestPrice = math.inf
					for startingSlot in range(startAfterSlot, finishBySlot - runtime):
						# calculate the price for if the appliance would be run starting at a given slot
						slotPrice = numpy.dot(powerUsageProfile, priceProfile[startingSlot:startingSlot+runtime])
						# if it's better than what we found so far, save it
						if slotPrice < cheapestPrice:
							cheapestSlot = startingSlot
							cheapestPrice = slotPrice
				
				# put the usage of the appliance at the right time in the power profile
				powerProfile[cheapestSlot:cheapestSlot+runtime] = powerUsageProfile
			
			# save the power profile
			self.smartDemand.add(midnight, powerProfile)
	
	# calculates appliance power demand for a given time interval acting as if the appliance wanted to be used as early as possible
	def calculateUncontrolledDemand(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		# for each day in the interval, just run the appliance as soon as possible
		for midnight in utils.midnightsBetween(fromDT, toDT):
			date = midnight.date()
			# the power profile of that day (plus some overlap)
			powerProfile = numpy.zeros(2 * utils.minutesIn(oneDay))
			
			# get the appliance usage for that day and act accordingly
			usage = self.memory.usages[date]
			if usage is not None:
				((startAfter, _), powerUsageProfile) = usage
				
				# the slots in which the appliance is available for being turned on
				startAfterSlot = startAfter.hour * 60 + startAfter.minute
				
				# the length of the run of the appliance
				runtime = powerUsageProfile.size
				
				# put the usage of the appliance at the right time in the power profile
				powerProfile[startAfterSlot:startAfterSlot+runtime] = powerUsageProfile
			
			# save the power profile
			self.uncontrolledDemand.add(midnight, powerProfile)
	
	# calculates appliance power demand for a given time interval acting as if the machine wanted to spread out its use across the whole possible interval
	def calculateSpreadOutDemand(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		# for each day in the interval, just run the appliance in the middle of the available interval
		for midnight in utils.midnightsBetween(fromDT, toDT):
			date = midnight.date()
			# the power profile of that day (plus some overlap)
			powerProfile = numpy.zeros(2 * utils.minutesIn(oneDay))
			
			# get the appliance usage for that day and act accordingly
			usage = self.memory.usages[date]
			if usage is not None:
				# the slots in which the appliance is available for being turned on
				((startAfter, finishBy), powerUsageProfile) = usage
				startAfterSlot = startAfter.hour * 60 + startAfter.minute
				finishBySlot = finishBy.hour * 60 + finishBy.minute + utils.minutesIn(oneDay)
				
				# the length of the run of the appliance
				runtime = powerUsageProfile.size
				
				# the slot in which the appliance should start
				startingSlot = startAfterSlot + max(0, (finishBySlot - startAfterSlot - runtime) // 2)
				
				# put the usage of the appliance at the right time in the power profile
				powerProfile[startingSlot:startingSlot+runtime] = powerUsageProfile
			
			# save the power profile
			self.spreadOutDemand.add(midnight, powerProfile)

# class representing an electric car
class Car(Battery):
	usageStatistics = applianceStatistics.carStatistics[0]
	@classmethod
	def randomWithIndex(cls, index: int = 0):
		usageStatistics = applianceStatistics.carStatistics[index]
		chargingPower = usageStatistics.randomChargingPower()
		car = cls(chargingPower=chargingPower)
		car.usageStatistics = usageStatistics
		return car

# class representing air conditioning
class AirConditioning(Accumulator):
	usageStatistics = applianceStatistics.airConditioningStatistics

# class representing an electrical heating
class ElectricalHeating(Accumulator):
	usageStatistics = applianceStatistics.electricalHeatingStatistics

# class representing a refrigerator
class Fridge(Accumulator):
	usageStatistics = applianceStatistics.fridgeStatistics

# class representing a water heater
class WaterHeater(Accumulator):
	usageStatistics = applianceStatistics.waterHeaterStatistics

# class representing a dishwasher
class Dishwasher(Machine):
	usageStatistics = applianceStatistics.dishwasherStatistics

# class representing a washing machine
class WashingMachine(Machine):
	usageStatistics = applianceStatistics.washingMachineStatistics

#!/usr/bin/env python3

import datetime
import random

from typing import List

import numpy

from . import applianceStatistics, utils

from .appliance import Appliance, Car, AirConditioning, ElectricalHeating, WaterHeater, Fridge, WashingMachine, Dishwasher
from .constants import oneDay
from .profile import Profile

# class representing a house connected to the smart grid
class House:
	# current date and time in the simulation
	currentDT: datetime.datetime
	# the appliances in this house
	appliances: List[Appliance]
	# the electricity prices for any given minute for this house
	priceProfile: Profile
	# the electricity demand if this house was using smart appliances
	smartDemand: Profile
	# the electricity demand if the appliances in this house would charge as early as possible
	uncontrolledDemand: Profile
	# the electricity demand if the appliances in this house would charge evenly over their use period
	spreadOutDemand: Profile
	
	# constructor, just sets up the variables
	def __init__(self):
		self.appliances = []
		self.priceProfile = Profile()
		self.smartDemand = Profile()
		self.uncontrolledDemand = Profile()
		self.spreadOutDemand = Profile()
	
	# creates a random house with random appliances according to appliance ownership statistics
	@classmethod
	def random(cls):
		h = cls()
		carCount = utils.randomWithRelativeProbs(applianceStatistics.carCountProbabilities)
		for car in range(carCount):
			h.addAppliance(Car.randomWithIndex(index=car))
		
		if random.random() < applianceStatistics.ownershipRatios.airConditioning:
			h.addAppliance(AirConditioning.random())
		if random.random() < applianceStatistics.ownershipRatios.electricalHeating:
			h.addAppliance(ElectricalHeating.random())
		if random.random() < applianceStatistics.ownershipRatios.waterHeater:
			h.addAppliance(WaterHeater.random())
		if random.random() < applianceStatistics.ownershipRatios.fridge:
			h.addAppliance(Fridge.random())
		if random.random() < applianceStatistics.ownershipRatios.washingMachine:
			h.addAppliance(WashingMachine.random())
		if random.random() < applianceStatistics.ownershipRatios.dishwasher:
			h.addAppliance(Dishwasher.random())
		return h
	
	# adds an appliance to the house
	def addAppliance(self, appliance: Appliance):
		self.appliances.append(appliance)
	
	# sets up the house for the simulation
	def setUp(self, dt: datetime.datetime):
		self.currentDT = dt
		# set up all the appliances in the house
		for appliance in self.appliances:
			appliance.setUp(dt)
	
	# moves ahead one day and does all the calculations that need to be done in that day
	def tick(self):
		# remove past, unneeded values from the profiles to free up some memory
		self.priceProfile.prune(self.currentDT - oneDay)
		self.smartDemand.prune(self.currentDT - oneDay)
		self.uncontrolledDemand.prune(self.currentDT - oneDay)
		self.spreadOutDemand.prune(self.currentDT - oneDay)
		
		# move ahead one day in all the appliances in this house as well
		for appliance in self.appliances:
			appliance.tick()
		
		# move the current time forward
		self.currentDT += oneDay
		
		# collect the electricity demands from all the appliances
		self.collectApplianceDemand(self.currentDT - oneDay, self.currentDT)
	
	# sets the electricity price profile for this house
	# called by the connection to the grid
	def setPriceProfile(self, dt: datetime.datetime, prices: numpy.ndarray):
		self.priceProfile.set(dt, prices)
		# pass on the price profile to all the appliances in this house
		for appliance in self.appliances:
			appliance.setPriceProfile(dt, prices)
	
	# gets the electricity demand if this house was using smart appliances
	def getSmartDemand(self, fromDT: datetime.datetime = None, toDT: datetime.datetime = None):
		return self.smartDemand.get(fromDT, toDT)
	
	# gets the electricity demand if this house was NOT using smart appliances
	def getUncontrolledDemand(self, fromDT: datetime.datetime = None, toDT: datetime.datetime = None):
		return self.uncontrolledDemand.get(fromDT, toDT)
	
	# gets the electricity demand if this house was NOT using smart appliances
	def getSpreadOutDemand(self, fromDT: datetime.datetime = None, toDT: datetime.datetime = None):
		return self.spreadOutDemand.get(fromDT, toDT)
	
	# collects the electricity demands from all the appliances in the house
	def collectApplianceDemand(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		for appliance in self.appliances:
			smartDemand = appliance.smartDemand.get(fromDT, toDT)
			uncontrolledDemand = appliance.uncontrolledDemand.get(fromDT, toDT)
			spreadOutDemand = appliance.spreadOutDemand.get(fromDT, toDT)
			self.smartDemand.add(fromDT, smartDemand)
			self.uncontrolledDemand.add(fromDT, uncontrolledDemand)
			self.spreadOutDemand.add(fromDT, spreadOutDemand)

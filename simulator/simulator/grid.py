#!/usr/bin/env python3

import datetime

from typing import List

import numpy
import scipy
import scipy.signal

from . import applianceStatistics
from . import gridStatistics
from . import utils

from .constants import oneDay
from .connection import Connection
from .house import House
from .profile import Profile

# smart grid main class
class Grid:
	# current date and time in the simulation
	currentDT: datetime.datetime
	# predicted base demand
	predictedBaseDemand: Profile
	# demand which the houses and their appliances should target
	targetDemand: Profile
	# demand from houses if they would be using smart appliances
	smartDemand: Profile
	# demand from houses if their appliances would charge as early as possible
	uncontrolledDemand: Profile
	# demand from houses if their appliances would charge evenly over their use period
	spreadOutDemand: Profile
	# how many households should be having cheap electricity at any given time
	cheapPriceRatio: Profile
	# connections to houses
	connections: List[Connection]
	
	# constructor, just prepares all the variables
	def __init__(self):
		self.predictedBaseDemand = Profile()
		self.targetDemand = Profile()
		self.smartDemand = Profile()
		self.uncontrolledDemand = Profile()
		self.spreadOutDemand = Profile()
		self.cheapPriceRatio = Profile()
		self.connections = []
		
	# connects a house to the grid
	def connectHouse(self, house: House):
		self.connections.append(Connection(house=house))
	
	# sets everything up before the start of the simulation
	def setUp(self, dt: datetime.datetime):
		self.currentDT = dt
		
		# predict base demand, calculate target demand and price ratios enough ahead in the future
		self.predictBaseDemand(fromDT=dt-3*oneDay, toDT=dt+4*oneDay)
		self.calculateTargetDemand(fromDT=dt-2*oneDay, toDT=dt+3.5*oneDay)
		self.calculatePriceRatio(fromDT=dt-1*oneDay, toDT=dt+2.5*oneDay)
		
		# pass the price ratios to the house connections
		self.distributePriceRatios(fromDT=dt-1*oneDay, toDT=dt+2.5*oneDay)
		
		# set up all the connections to the houses
		for conn in self.connections:
			conn.setUp(dt)
	
	# moves ahead one day and does all the calculations that need to be done in that day
	def tick(self):
		self.currentDT += oneDay
		cdt = self.currentDT
		
		# gather and save power demands from all the houses
		self.collectDemands(fromDT=cdt-oneDay, toDT=cdt)
		
		# predict base demand for one more day
		self.predictBaseDemand(fromDT=cdt+3*oneDay, toDT=cdt+4*oneDay)
		
		# calculate target demand and price ratios for one more day
		self.calculateTargetDemand(fromDT=cdt+2.5*oneDay, toDT=cdt+3.5*oneDay)
		self.calculatePriceRatio(fromDT=cdt+1.5*oneDay, toDT=cdt+2.5*oneDay)
		
		# pass the new price ratios to the house connections
		self.distributePriceRatios(fromDT=cdt+1.5*oneDay, toDT=cdt+2.5*oneDay)
		
		# move ahead one day in all the connections to houses as well
		for conn in self.connections:
			conn.tick()
	
	# predicts the power demand on the grid without the connected houses
	def predictBaseDemand(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		# right now this just takes the total demand forecast and subtracts the recorded draw from households during the specified interval
		# in an actual grid this would do some fancy calculations to get the prediction
		demandForecast = gridStatistics.demandForecast.demand.get(fromDT, toDT) * (len(self.connections) / gridStatistics.demandForecast.householdCount)
		householdDraw = gridStatistics.averageHouseholdDraw.get(fromDT, toDT) * len(self.connections)
		
		baseDemandPrediction = demandForecast - householdDraw
		
		self.predictedBaseDemand.set(fromDT, baseDemandPrediction)
	
	# calculates the target demand for the connected houses, based on the base demand, household power usage estimates (and power generation predictions, if available)
	def calculateTargetDemand(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		# right now this just calculates a demand that smooths out the base demand and is big enough to cover all the needs of the households
		# in an actual grid this would also take into account the power generation predictions (solar and wind generation, power plant shutdowns etc)
		
		# calculate the expected household demand in the given interval
		# get power usage estimates for all the simulated appliances for each day in the interval and sum them together
		totalExpectedConsumption = 0.0
		for fraction, day in utils.dayPortionsBetween(fromDT, toDT):
			expectedDayConsumption = 0.0
			for carIndex in range(4):
				expectedDayConsumption += applianceStatistics.atLeastThisManyCarsProbability[carIndex+1] * applianceStatistics.carStatistics[carIndex].averageNeededCharge[day]
			expectedDayConsumption += applianceStatistics.ownershipRatios.airConditioning * applianceStatistics.airConditioningStatistics.averageDailyCharge[day]
			expectedDayConsumption += applianceStatistics.ownershipRatios.electricalHeating * applianceStatistics.electricalHeatingStatistics.averageDailyCharge[day]
			expectedDayConsumption += applianceStatistics.ownershipRatios.fridge * applianceStatistics.fridgeStatistics.averageDailyCharge[day]
			expectedDayConsumption += applianceStatistics.ownershipRatios.waterHeater * applianceStatistics.waterHeaterStatistics.averageDailyCharge[day]
			expectedDayConsumption += applianceStatistics.ownershipRatios.dishwasher * applianceStatistics.dishwasherStatistics.averagePowerNeeded[day]
			expectedDayConsumption += applianceStatistics.ownershipRatios.washingMachine * applianceStatistics.washingMachineStatistics.averagePowerNeeded[day]
			
			totalExpectedConsumption += fraction * len(self.connections) * expectedDayConsumption
		
		# introduce some error in the statistics
		totalExpectedConsumption *= 0.9 + numpy.random.random() * 0.2
		
		# find peaks in the base demand and interpolate between them to get a smooth curve
		# have some margin at the ends of the desired interval to have a better interpolation
		startMargin = oneDay
		endMargin = 0.5*oneDay
		startIndex = utils.minutesIn(startMargin)
		
		baseDemand = self.predictedBaseDemand.get(fromDT-startMargin, toDT+endMargin)
		
		peaks = list(scipy.signal.find_peaks(baseDemand, distance=18*60, width=10)[0])
		
		peakLocs = [0] + peaks + [baseDemand.size-1]
		peakVals = baseDemand[[peaks[0]] + peaks + [peaks[-1]]]
		
		if len(peakLocs) > 3:
			interpolationKind = 'cubic'
		else:
			interpolationKind = 'quadratic'
		
		smoothDemand = scipy.interpolate.interp1d(peakLocs, peakVals, kind=interpolationKind)(range(baseDemand.size))
		
		# set the target household demand as the difference between the smooth demand and the base demand
		targetDemand = (smoothDemand - baseDemand)[startIndex:]
		
		# calculate the integral of the target demand
		intervalLength = utils.minutesBetween(fromDT, toDT)
		totalTargetIntervalConsumption = numpy.sum(targetDemand[:intervalLength]) / 60
		
		if totalExpectedConsumption <= totalTargetIntervalConsumption:
			# if the total target consumption is higher than the expected demand of the households, scale it down
			targetDemand *= (totalExpectedConsumption / totalTargetIntervalConsumption)
		else:
			# otherwise shift the target demand up so it covers all the needs of the households
			targetDemand += ((totalExpectedConsumption - totalTargetIntervalConsumption) / (intervalLength / 60))
		
		# negative demand is not possible in this simulation (eventually could be with vehicle-to-grid systems)
		targetDemand = numpy.maximum(targetDemand, 0)
		
		# the target demand calculations between the previous interval and this interval possibly don't join nicely
		# we have to smoothly transition from the previously calculated target demand to the new one (there should be a 12-hour overlap)
		self.targetDemand.transition(fromDT=fromDT, newValues=targetDemand)
	
	# calculates price ratios based on the target demand and appliance availability statistics
	# more households should have a cheap electricity price when the target demand is higher
	def calculatePriceRatio(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		# get the target demand with some margin at the ends of the desired interval for a better interpolation
		startMargin = oneDay
		endMargin = oneDay
		startIndex = utils.minutesIn(startMargin)
		
		targetDemand = self.targetDemand.get(fromDT-startMargin, toDT+endMargin)
		
		# scale the target demand based on how many appliances are available to be turned on
		# right now the only appliances that matter and are not available continuously are cars
		# dishwashers and washing machines contribute so little to the total power consumption that scaling based on their usage intervals doesn't really make sense
		
		# get the ratio of how much of the target demand is expected to be used by cars
		totalExpectedCarConsumption = 0.0
		for fraction, day in utils.dayPortionsBetween(fromDT-startMargin, toDT+endMargin):
			for carIndex in range(4):
				totalExpectedCarConsumption += fraction * len(self.connections) * applianceStatistics.atLeastThisManyCarsProbability[carIndex+1] * applianceStatistics.carStatistics[carIndex].averageNeededCharge[day]
		carDemandRatio = totalExpectedCarConsumption / numpy.sum(targetDemand)
		
		# get the statistics for how many cars that need a charge are likely to be at home
		totalNeedChargingRatio = 0
		carsAtHome = numpy.zeros(utils.minutesBetween(fromDT-startMargin, toDT+endMargin))
		for carIndex in range(4):
			needChargingRatio = 0
			totalFraction = 0
			for fraction, day in utils.dayPortionsBetween(fromDT-startMargin, toDT+endMargin):
				needChargingRatio += fraction * applianceStatistics.carStatistics[carIndex].usageProbabilities[day]
				totalFraction += fraction
			needChargingRatio /= totalFraction
			carsAtHome += needChargingRatio * applianceStatistics.carStatistics[carIndex].availabilityProfile.get(fromDT-startMargin, toDT+endMargin)
			totalNeedChargingRatio += needChargingRatio
		carsAtHome /= totalNeedChargingRatio
		
		# we need to give more households cheaper prices when there are less cars at home, so those that are at home would charge and cover the target demand
		availabilityScale = (1 - carDemandRatio) + carDemandRatio * carsAtHome
		relativeTargetDemand = targetDemand / availabilityScale
		
		# we need to make sure the peaks each day correspond to cheap prices for all households
		# therefore we need to scale the (already scaled) target demand so that the peaks each day scale to 1, to get nice probabilities
		# get the peaks in the relative target demand, approximately one each day
		peaks = list(scipy.signal.find_peaks(relativeTargetDemand, distance=18*60, width=10)[0])
		peakLocs = [0] + peaks + [relativeTargetDemand.size-1]
		peakVals = relativeTargetDemand[[peaks[0]] + peaks + [peaks[-1]]]
		
		# interpolate between the peaks, to get a smoothed out rolling maximum curve
		demandScale = utils.cosineInterpolation(peakLocs, peakVals)
		# divide the relative target demand by the smoothed out maximum curve, to scale the peaks to 1 to get the price ratio
		scaledDemand = relativeTargetDemand / demandScale
		cheapPriceRatio = scaledDemand[startIndex:]
		
		# the price ratio calculations between the previous interval and this one might not join nicely
		# we have to smoothly transition from the previously calculated price ratios to the new ones (there should be a 24-hour overlap)
		self.cheapPriceRatio.transition(fromDT, cheapPriceRatio)
	
	# distributes the calculated price ratios to all the connections
	def distributePriceRatios(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		cheapPriceRatio = self.cheapPriceRatio.get(fromDT, toDT)
		for conn in self.connections:
			conn.setPriceRatio(fromDT, cheapPriceRatio)
	
	# collects the power demands from all the connected households
	def collectDemands(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		length = utils.minutesBetween(fromDT, toDT)
		smartDemand = numpy.zeros(length)
		uncontrolledDemand = numpy.zeros(length)
		spreadOutDemand = numpy.zeros(length)
		for conn in self.connections:
			smartDemand += conn.getSmartDemand(fromDT, toDT)
			uncontrolledDemand += conn.getUncontrolledDemand(fromDT, toDT)
			spreadOutDemand += conn.getSpreadOutDemand(fromDT, toDT)
		
		self.smartDemand.set(fromDT, smartDemand)
		self.uncontrolledDemand.set(fromDT, uncontrolledDemand)
		self.spreadOutDemand.set(fromDT, spreadOutDemand)

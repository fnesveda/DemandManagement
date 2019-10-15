#!/usr/bin/env python3

import datetime

import numpy

from . import utils
from . import priceConfig

from .constants import oneDay
from .house import House
from .profile import Profile

# class for the connections between the smart grid and houses
class Connection:
	# current date and time in the simulation
	currentDT: datetime.datetime
	# the connected house
	house: House
	# probabilities with which the electricity price should be lower in a given minute
	cheaperPriceRatioProfile: Profile
	# times where the prices will be cheaper
	cheaperMinutesProfile: Profile
	# the actual price profile for the connected house
	priceProfile: Profile
	
	# constructor, just prepares the variables
	def __init__(self, house: House):
		self.house = house
		self.cheaperPriceRatioProfile = Profile()
		self.cheaperMinutesProfile = Profile()
		self.priceProfile = Profile()
	
	# sets everything up before the start of the simulation
	def setUp(self, dt: datetime.datetime):
		self.currentDT = dt
		# set up the house as well
		self.house.setUp(dt=dt)
		
		# generate cheaper price intervals and the electricity price profile ahead enough in the future
		self.generateRandomCheaperIntervals(dt-1*oneDay, dt+2*oneDay)
		self.generatePriceProfile(dt-1*oneDay, dt+2*oneDay)
		
		# send the generated price profile to the connected house
		self.sendPriceProfile(dt-1*oneDay, dt+2*oneDay)
	
	# moves ahead one day and does all the calculations that need to be done in that day
	def tick(self):
		# remove past, unneeded values from the profiles to free up some memory
		self.cheaperPriceRatioProfile.prune(self.currentDT - oneDay)
		self.cheaperMinutesProfile.prune(self.currentDT - oneDay)
		self.priceProfile.prune(self.currentDT - oneDay)
		
		# move one day ahead
		self.currentDT += oneDay
		cdt = self.currentDT
		
		# generate cheaper price intervals and the electricity price profile for one more day
		self.generateRandomCheaperIntervals(cdt+oneDay, cdt+2*oneDay)
		self.generatePriceProfile(cdt+oneDay, cdt+2*oneDay)
		
		# send the generated price profile to the connected house
		self.sendPriceProfile(cdt+oneDay, cdt+2*oneDay)
	
	# generates intervals of cheaper prices based on the cheap price probabilities provided by the smart grid
	def generateRandomCheaperIntervals(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		# how many minutes continuously have to be cheap (60 minutes by default)
		cheapIntervalLength = priceConfig.cheapIntervalLength
		# at least how many minutes in total have to be cheap per day
		cheapMinutesTotal = priceConfig.cheapMinutesCount
		
		# if it is configured to have zero minutes cheap, we act as if there was no lower or upper limit on the minutes
		if cheapMinutesTotal == 0:
			# get probabilities for the connected house having cheaper electricity at a given minute
			probs = self.cheaperPriceRatioProfile.get(fromDT, toDT)
			# generate the positions of the cheaper minutes and save them
			cheaperMinutes = numpy.random.random(probs.size) < probs
			self.cheaperMinutesProfile.add(fromDT, cheaperMinutes)
		
		# otherwise we guarantee to have the specified amount of minutes cheap
		else:
			# generate cheaper intervals for each day that starts in the given interval
			for midnight in utils.midnightsBetween(fromDT, toDT):
				# start with all prices expensive
				cheaperIntervals = numpy.zeros(utils.minutesIn(oneDay)+2*cheapIntervalLength)
				
				# get probabilities for a cheap interval being positioned in a given spot
				# we can't change prices for previous days already broadcasted to houses, so we need to make sure the intervals we set will start after midnight of the previous day
				shift = datetime.timedelta(minutes=cheapIntervalLength)
				probs = self.cheaperPriceRatioProfile.get(midnight+shift, midnight+shift+oneDay)
				
				# this distinction is just to optimize the calculation, the results are the same
				if cheapIntervalLength == 1:
					# generate enough cheap minutes in the given day
					cheapMinutePositions = utils.randomWithRelativeProbs(probs, count=cheapMinutesTotal)
					cheaperIntervals[cheapMinutePositions] = 1
				else:
					# add cheap intervals until there are enough cheap minutes in the given day
					# some intervals might overlap and that is okay
					while numpy.sum(cheaperIntervals) < cheapMinutesTotal:
						# put a cheap interval in a random position
						cheapIntervalStart = utils.minutesIn(shift) + utils.randomWithRelativeProbs(probs) - cheapIntervalLength//2
						cheaperIntervals[cheapIntervalStart:cheapIntervalStart+cheapIntervalLength] = 1
				
				# save the cheaper intervals
				self.cheaperMinutesProfile.add(midnight, cheaperIntervals)
	
	# generates a price profile based on the cheaper interval locations calculated earlier
	def generatePriceProfile(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		# the electricity prices
		lowerPrice = priceConfig.lowerPrice
		higherPrice = priceConfig.higherPrice
		
		# get where the price should be cheaper
		cheapIntervals = numpy.minimum(self.cheaperMinutesProfile.get(fromDT, toDT), 1)
		
		# set the prices accordingly
		prices = numpy.full(cheapIntervals.size, fill_value=higherPrice, dtype=float)
		prices[cheapIntervals.astype(bool)] = lowerPrice
		
		# add a bit of randomness so appliances don't always choose the earliest possible cheap location
		prices += numpy.random.random(prices.size) * 0.01
		
		# save the price profile
		self.priceProfile.set(fromDT, prices)
	
	# sends the price profile to the connected house
	def sendPriceProfile(self, fromDT: datetime.datetime, toDT: datetime.datetime):
		prices = self.priceProfile.get(fromDT, toDT)
		self.house.setPriceProfile(fromDT, prices)
	
	# sets the probabilities that the electricity will be cheaper in a given minute
	# called by the grid
	def setPriceRatio(self, fromDT: datetime.datetime, priceRatio: numpy.ndarray):
		self.cheaperPriceRatioProfile.set(fromDT, priceRatio)
	
	# collect the electricity demand the house would have if it was using smart appliances
	# called by the grid
	def getSmartDemand(self, fromDT: datetime.datetime = None, toDT: datetime.datetime = None):
		return self.house.getSmartDemand(fromDT, toDT)
	
	# collect the electricity demand the house would have if its appliances would charge as early as possible
	# called by the grid
	def getUncontrolledDemand(self, fromDT: datetime.datetime = None, toDT: datetime.datetime = None):
		return self.house.getUncontrolledDemand(fromDT, toDT)
	
	# collect the electricity demand the house would have if its appliances would charge evenly over their use period
	# called by the grid
	def getSpreadOutDemand(self, fromDT: datetime.datetime = None, toDT: datetime.datetime = None):
		return self.house.getSpreadOutDemand(fromDT, toDT)

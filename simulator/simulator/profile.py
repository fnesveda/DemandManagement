#!/usr/bin/env python3

import datetime
from typing import Dict

import numpy
import pandas

from .utils import minutesBetween

# helper class to deal with time series
class Profile:
	# date and time of the first stored value
	startingDT: datetime.datetime
	# the actual stored values
	values: numpy.ndarray
	
	# constructor
	def __init__(self, startingDT: datetime.datetime = None, values: numpy.ndarray = None):
		self.startingDT = startingDT
		if values is None or startingDT is None:
			self.values = numpy.empty(0)
		else:
			self.values = values.copy()
	
	# get values between fromDT and toDT, return zeros if the values are missing
	def get(self, fromDT: datetime.datetime, toDT: datetime.datetime = None):
		if self.startingDT is None:
			if toDT is None:
				raise IndexError()
			else:
				length = minutesBetween(fromDT, toDT)
				return numpy.zeros(length)
		
		startIndex = minutesBetween(self.startingDT, fromDT)
		if toDT is None:
			if startIndex < 0 or startIndex >= self.values.size:
				return 0
			else:
				return self.values[startIndex]
		else:
			length = minutesBetween(fromDT, toDT)
			res = numpy.zeros(length, dtype=float)
			stopIndex = min(self.values.size, minutesBetween(self.startingDT, toDT))
			res[:stopIndex-startIndex] = self.values[startIndex:stopIndex]
			return res
	
	# set values starting at fromDT to newValues
	def set(self, fromDT: datetime.datetime, newValues: numpy.ndarray):
		if self.startingDT is None:
			self.startingDT = fromDT
			self.values = newValues.copy()
		else:
			startIndex = minutesBetween(self.startingDT, fromDT)
			newSize = startIndex + newValues.size
			
			if newSize > self.values.size:
				self.values.resize(newSize, refcheck=False)
			
			self.values[startIndex:startIndex+newValues.size] = newValues
	
	# add up values in valuesToAdd to currently stored values starting at fromDT
	def add(self, fromDT: datetime.datetime, valuesToAdd: numpy.ndarray):
		if self.startingDT is None:
			self.startingDT = fromDT
		
		startIndex = minutesBetween(self.startingDT, fromDT)
		newSize = startIndex + valuesToAdd.size
		
		if newSize > self.values.size:
			self.values.resize(newSize, refcheck=False)
		self.values[startIndex:startIndex+valuesToAdd.size] += valuesToAdd
	
	# smoothly transition from the currently stored values to newValues starting at fromDT using a cosine interpolation
	def transition(self, fromDT: datetime.datetime, newValues: numpy.ndarray):
		if self.startingDT is None:
			self.set(fromDT, newValues)
		else:
			startIndex = minutesBetween(self.startingDT, fromDT)
			overlappingValues = self.values.size - startIndex
			
			newSize = startIndex + newValues.size
			if newSize > self.values.size:
				self.values.resize(newSize, refcheck=False)
			
			if overlappingValues == 0:
				self.values = numpy.append(self.values, newValues)
			elif overlappingValues < 0:
				self.values[startIndex:] = newValues
			else:
				oldValues = self.values[startIndex:]
				ratio = (numpy.cos(numpy.linspace(0, numpy.pi, num=overlappingValues, endpoint=False)) + 1) / 2
				oldMask = numpy.pad(ratio, (0, newValues.size - overlappingValues), mode='constant', constant_values=0)
				newMask = numpy.pad(1-ratio, (0, newValues.size - overlappingValues), mode='constant', constant_values=1)
				self.values[startIndex:] = oldValues * oldMask + newValues * newMask
	
	# multiply the stored values by scale
	def scale(self, scale):
		self.values *= scale
		
	# delete stored values up to, but not including, toDT
	def prune(self, toDT: datetime.datetime):
		if self.startingDT is None:
			return
		if toDT <= self.startingDT:
			return
		
		index = minutesBetween(self.startingDT, toDT)
		self.startingDT = toDT
		self.values = self.values[index:].copy()
	
	# return a copy of this Profile
	def copy(self):
		return Profile(self.startingDT, self.values.copy())
	
	# return a dictionary of the averate of stored values for each date in this Profile
	def dailyAverages(self) -> Dict[datetime.date, float]:
		if self.startingDT is None or self.values.size == 0:
			return {}
		
		averages = {}
		
		currentDate = self.startingDT.date()
		startIndex = minutesBetween(self.startingDT, currentDate)
		endIndex = startIndex + 24*60
		
		while startIndex < self.values.size:
			dayValues = self.values[max(0, startIndex):min(endIndex, self.values.size)]
			averages[currentDate] = numpy.mean(dayValues)
			
			currentDate += datetime.timedelta(days=1)
			startIndex += 24*60
			endIndex += 24*60
		return averages
	
	@classmethod
	def fromCSV(cls, path):
		data = pandas.read_csv(path, parse_dates=[0])
		startingDT = data.iloc[0, 0].to_pydatetime()
		values = data.iloc[:, 1].values
		return cls(startingDT, values)

#!/usr/bin/env python3

import datetime
from typing import List, Tuple

import numpy

from .constants import oneDay

# helper functions frequently used in the simulator

# counts the minutes in a timedelta object
def minutesIn(td: datetime.timedelta) -> int:
	return int(td.total_seconds() // 60)

# counts the minutes between two datetimes
def minutesBetween(startDT: datetime.datetime, endDT: datetime.datetime) -> int:
	if isinstance(startDT, datetime.date) and not isinstance(startDT, datetime.datetime):
		startDT = datetime.datetime.combine(startDT, datetime.time())
	if isinstance(endDT, datetime.date) and not isinstance(endDT, datetime.datetime):
		endDT = datetime.datetime.combine(endDT, datetime.time())
	return minutesIn(endDT - startDT)

# returns the midnights between two datetimes
def midnightsBetween(startDT: datetime.datetime, endDT: datetime.datetime) -> List[datetime.datetime]:
	midnights = []
	if (startDT.hour, startDT.minute, startDT.second, startDT.microsecond) == (0, 0, 0, 0):
		midnights.append(startDT)
	currentDT = startDT.replace(hour=0, minute=0, second=0, microsecond=0) + oneDay
	while currentDT < endDT:
		midnights.append(currentDT)
		currentDT += oneDay
	return midnights

# returns the days between two datetimes, and for each day also a fraction which is covered in the given interval
def dayPortionsBetween(startDT: datetime.datetime, endDT: datetime.datetime) -> List[Tuple[float, datetime.date]]:
	if startDT >= endDT:
		return []
	elif startDT.date() == endDT.date():
		return [((endDT - startDT).total_seconds() / (24*60*60), startDT.date())]
	else:
		portions = []
		currentDT = startDT
		nextMidnight = startDT.replace(hour=0, minute=0, second=0, microsecond=0) + oneDay
		while nextMidnight <= endDT:
			portions.append(((nextMidnight - currentDT).total_seconds() / (24*60*60), currentDT.date()))
			currentDT = nextMidnight
			nextMidnight = currentDT + oneDay
		if currentDT < endDT:
			portions.append(((endDT - currentDT).total_seconds() / (24*60*60), currentDT.date()))
		return portions

# randomly choose an integer with relative probabilities provided in an array
def randomWithRelativeProbs(relativeProbs: numpy.ndarray, count: int = None):
	if not isinstance(relativeProbs, numpy.ndarray):
		relativeProbs = numpy.array(relativeProbs)
	probs = relativeProbs / numpy.sum(relativeProbs)
	if count is None:
		return numpy.random.choice(probs.size, p=probs)
	else:
		return numpy.random.choice(probs.size, size=count, replace=False, p=probs)

# perform a cosine interpolation from a list of coordinates
def cosineInterpolation(xs: List[int], ys: List[float]) -> numpy.ndarray:
	res = []
	for x1, x2, y1, y2 in zip(xs[:-1], xs[1:], ys[:-1], ys[1:]):
		ratio = (numpy.cos(numpy.linspace(0, numpy.pi, num=x2-x1, endpoint=False)) + 1) / 2
		vals = y1 * ratio + y2 * (1 - ratio)
		res.extend(vals)
	res.append(ys[-1])
	return numpy.array(res)

#!/usr/bin/env python3

import os

from types import SimpleNamespace

from .profile import Profile

thisDir = os.path.dirname(__file__)

# class for representing statistics of grid electricity demand
class GridDemandStatistics(SimpleNamespace):
	# households connected to the grid
	householdCount: int
	# electricity demand profile of the grid
	demand: Profile

# 4-day-ahead prediction of the Texas grid electricity demand
demandForecast = GridDemandStatistics()
demandForecast.demand = Profile.fromCSV(f"{thisDir}/data/dataport/ercot/predictions/96.csv")
demandForecast.householdCount = 9500000


# actual Texas grid electricity demand
actualDemand = GridDemandStatistics()
actualDemand.demand = Profile.fromCSV(f"{thisDir}/data/dataport/ercot/actual/systemLoad.csv")
actualDemand.householdCount = 9500000

# average power usage of a household
averageHouseholdDraw = Profile.fromCSV(f"{thisDir}/data/dataport/household/averageDraw.csv")

#!/usr/bin/env python3

import datetime
import gc
import os
import time

import pandas

from . import gridStatistics, priceConfig

from .constants import oneDay
from .grid import Grid
from .house import House

# smart grid simulator main class
class Simulator:
	# run the smart grid simulation
	@classmethod
	def run(cls, startingDT: datetime.datetime, simulationLength: int, houseCount: int, outputFolder: str = None):
		# remember the starting time
		st = time.time()
		# create the grid
		print("Creating grid...")
		grid = Grid()
		
		# create random houses and connect them to the grid
		print("Creating houses...")
		houses = []
		for _ in range(houseCount):
			h = House.random()
			grid.connectHouse(h)
			houses.append(h)
			
		# set up the grid with the right time
		# the grid sets up the connected houses itself
		print("Setting up grid...")
		grid.setUp(startingDT)
		
		print("Preparation took {:.3f}s".format(time.time() - st))
		print()
		
		# for each day of the simulation, send tick signals to the grid and houses for them to tell them time has moved
		# this is to make it easier to possibly change to a simulator architecture with multiple processes
		# where the simulator only provides the clock signal and the grid and houses take care of everything else
		endDT = startingDT + simulationLength * oneDay
		currentDT = startingDT
		while currentDT < endDT:
			print("Calculating power draw for", currentDT.date())
			t = time.time()
			for i, h in enumerate(houses):
				print(f"\r{i+1}/{houseCount}... ", end="")
				h.tick()
			grid.tick()
			# call garbage collection manually to ease memory pressure
			gc.collect()
			print("Calculation took {:.3f}s".format(time.time() - t))
			print()
			currentDT += oneDay
		
		print("Simulation took {:.3f}s in total".format(time.time() - st))
		print()
		
		# collect the results from the grid
		predictedBaseDemand = grid.predictedBaseDemand.get(startingDT, endDT)
		targetDemand = grid.targetDemand.get(startingDT, endDT)
		priceRatio = grid.cheapPriceRatio.get(startingDT, endDT)
		smartDemand = grid.smartDemand.get(startingDT, endDT)
		uncontrolledDemand = grid.uncontrolledDemand.get(startingDT, endDT)
		spreadOutDemand = grid.spreadOutDemand.get(startingDT, endDT)
		
		# get the actual grid base demand
		actualDemand = gridStatistics.actualDemand.demand.get(startingDT, endDT) * (houseCount / gridStatistics.actualDemand.householdCount)
		householdDraw = gridStatistics.averageHouseholdDraw.get(startingDT, endDT) * houseCount
		actualBaseDemand = actualDemand - householdDraw
		
		# prepare the datetime column
		datetimes = [startingDT + datetime.timedelta(minutes=i) for i in range(simulationLength*24*60)]
		
		# gather the results in a pandas dataframe
		data = pandas.DataFrame({
			"Datetime": datetimes,
			"PredictedBaseDemand": predictedBaseDemand,
			"ActualBaseDemand": actualBaseDemand,
			"TargetDemand": targetDemand,
			"SmartDemand": smartDemand,
			"UncontrolledDemand": uncontrolledDemand,
			"SpreadOutDemand": spreadOutDemand,
			"PriceRatio": priceRatio,
		})
		
		# save the results to a folder if specified
		if outputFolder is not None:
			os.makedirs(outputFolder, exist_ok=True)
			
			# save the simulation parameters to a separate file
			with open(f"{outputFolder}/desc.txt", "w+") as descfile:
				descfile.write(f"startingDatetime={startingDT}\n")
				descfile.write(f"simulationLength={simulationLength}\n")
				descfile.write(f"houseCount={houseCount}\n")
				descfile.write(f"lowerPrice={priceConfig.lowerPrice}\n")
				descfile.write(f"higherPrice={priceConfig.higherPrice}\n")
				descfile.write(f"cheapIntervalLength={priceConfig.cheapIntervalLength}\n")
				descfile.write(f"cheapMinutesTotal={priceConfig.cheapMinutesCount}\n")
			
			# save the demand values to a csv
			data.to_csv(f"{outputFolder}/data.csv", index=False, header=True, float_format="%.5f")
		
		# return results
		return data

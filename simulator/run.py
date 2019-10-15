#!/usr/bin/env python3

import datetime
import sys

def usage():
	print(f"Usage: {sys.argv[0]} startingDate simulationLength houseCount outputFolder")

if len(sys.argv) != 5:
	usage()
	sys.exit(1)

try:
	startingDate = datetime.datetime.strptime(sys.argv[1], "%Y-%m-%d")
	simulationLength = max(0, int(sys.argv[2]))
	houseCount = max(0, int(sys.argv[3]))
	outputFolder = sys.argv[4] # mostly anything can be a path under POSIX, this would be too hard to validate anyway
except ValueError:
	usage()
	sys.exit(1)

# importing after already running code is evil, I know
# but this takes a long time and would just delay the parameter checking
from simulator import Simulator

Simulator.run(startingDate, simulationLength, houseCount, outputFolder)

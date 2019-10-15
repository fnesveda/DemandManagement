Smart grid simulator
====================

This is a simulator of a smart grid made as a part of the masters thesis "Demand control in smart grids" at the Faculty of Mathematics and Physics of the Charles University in Prague.
It serves to simulate an electrical grid with households and appliances based on data from the National Household Travel Survey
and the Pecan Street organization research program,
while the appliances act according to several demand control algorithms described in the thesis,
which is included in the file _thesis.pdf_.

Requirements
------------

The simulator can be run in an UNIX environment containing the Bash shell and a Python interpreter version 3.6 or newer.
Several third-party Python libraries are required, these are listed in the file _requirements.txt_
and available for installation with the shell command `pip3 install -r requirements.txt`.

Data download
-------------
Before the actual usage of the simulator, the data necessary for the simulation must be downloaded first.
This is performed in three steps:

1. In the file _simulator/data/config.txt_, put the desired dates in the `fromdate` and `todate` fields, in the format `YYYY-MM-DD`. For a succesful simulation,
the data must be downloaded for an interval starting one week before the starting date of the simulation
and ending one week after the ending date of the simulation.

2. In the file _simulator/data/dataport/KEY_, put the username and password
to access the Dataport database in the `username` and `password` fields, respectively.
These access credentials can be obtained at https://dataport.pecanstreet.org/.

3. Execute the data download by using the command script `./downloadData.sh` in a terminal while being in the directory with the project.
Depending on the length of the downloaded interval, the download can take several hours and use several gigabytes of data.
Progress of the download is printed to the terminal during the run of the script.

Running the simulator
---------------------

After the data is downloaded, the simulator can be executed by using the command
`./run.py startingDate simulationLength householdCount outputFolder` in a terminal while being in the directory with the project,
while replacing `startingDate` with the date from which to run the simulation in the format `YYYY-MM-DD`,
`simulationLength` with the number of days to simulate,
`householdCount` with the number of households to simulate
and `outputFolder` with the destination folder in which the simulation results should be saved,
for example: `./run.py 2018-01-01 365 10000 out/`.

While the simulation is running, the simulator prints information about its progress to the terminal.
When the simulation finishes, the results are saved in the specified folder in two files, _desc.txt_ and _data.csv_.
The file _desc.txt_ contains information about the simulation parameters,
and the file _data.csv_ is a standard comma-separated values file containing the simulation results organized to eight columns:

Column              | Description
--------------------|------------
Datetime            | The date and time of the result
PredictedBaseDemand | The predicted grid base demand at that date and time (in kilowatts)
ActualBaseDemand    | The actual grid base demand at that date and time (in kilowatts)
TargetDemand        | The target power demand at that date and time (in kilowatts)
SmartDemand         | The power demand of the simulated households at that date and time if the smart algorithm was used (in kilowatts)
UncontrolledDemand  | The power demand of the simulated households at that date and time if the uncontrolled algorithm was used (in kilowatts)
SpreadOutDemand     | The power demand of the simulated households at that date and time if the spread out algorithm was used (in kilowatts)
PriceRatio          | The ratio of how many households should have a lower electricity price at that date and time

Displaying the results
----------------------

To display the simulation results, one can use the included Jupyter notebook
_Results.ipynb_. After opening the notebook, first the folder with the simulation
results must be specified in the variable _resultsFolder_ in the third code cell,
and then the cells in the notebook can be executed to show the results.

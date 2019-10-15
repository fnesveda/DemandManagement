#!/usr/bin/env bash

export PYTHONUNBUFFERED=1

echo "Retreiving NHTS data..."

cd cars
./getData.py $1 $2 | stdbuf -oL sed 's/^/    /'

echo "NHTS data retrieved."

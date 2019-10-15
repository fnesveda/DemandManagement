#!/usr/bin/env bash

export PYTHONUNBUFFERED=1

while read -r line || [ -n "$line" ]; do
	declare "$line";
done < KEY

DIRS=(accumulators machines cars household ercot)

echo "Retreiving dataport data..."

for dir in ${DIRS[@]}; do
	pushd $dir > /dev/null
	./getData.py $1 $2 $username $password | stdbuf -oL sed 's/^/    /'
	popd > /dev/null
done

echo "Dataport data retrieved."

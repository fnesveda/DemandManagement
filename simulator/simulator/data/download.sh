#!/usr/bin/env bash

pushd "$(dirname ${BASH_SOURCE[0]})" > /dev/null

while read -r line || [ -n "$line" ]; do
	declare "$line";
done < config.txt

DIRS=(dataport nhts)

echo "Retreiving data..."

for dir in ${DIRS[@]}; do
	pushd $dir > /dev/null
	./download.sh $fromdate $todate | stdbuf -oL sed 's/^/    /'
	popd > /dev/null
done

echo "Data retrieved."

popd > /dev/null
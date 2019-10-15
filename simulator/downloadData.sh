#!/usr/bin/env bash

DIR=$(dirname "${BASH_SOURCE[0]}")
pushd "${DIR}" > /dev/null
simulator/data/download.sh
popd > /dev/null

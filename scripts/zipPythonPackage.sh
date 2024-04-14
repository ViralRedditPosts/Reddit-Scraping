#!/bin/bash
# This is a script to download a python package binaries and zip it
# The intention is to use that package as a layer for a lambda function (or something else).
# use: 
#   sh zipPythonPackage.sh praw==7.7.0 boto3==1.26.117
# as you can see, packages are just listed as non-option arguments
# based on https://www.linkedin.com/pulse/add-external-python-libraries-aws-lambda-using-layers-gabe-olokun/
# Note: an old version of this script also moved the zip file to s3, this functionality has been removed.
# you may need to run chmod +x ./zipPythonPackage.sh

set -e

echo "packages: $@";

SCRIPT_PATH=${0%/*}  # https://stackoverflow.com/questions/6393551/what-is-the-meaning-of-0-in-a-bash-script
CWD=${pwd}
cd $SCRIPT_PATH

for package in "$@"; do
  echo "Preparing ${package}..."
  # format the zip file. needed for the git packages which have lots of slashes.
  if [[ ${package} == "git+"* ]]; then
    package_name=${package##*/}  # https://stackoverflow.com/questions/3162385/how-to-split-a-string-in-shell-and-get-the-last-field
  else
    package_name=${package}
  fi
  mkdir -p ./zippedPythonPackages/${package_name}/python

  cd ./zippedPythonPackages/${package_name}/python

  # install binaries for package
  pip install \
      --platform manylinux2014_x86_64 \
      --target=. \
      --implementation cp \
      --only-binary=:all: \
      --upgrade ${package}

  rm -rf *dist-info  # some cleanup of unnecessary stuff
  # zip package
  cd ..
  rm -rf ${package_name}.zip # remove first if it exists
  echo "Zipping ${package_name} at $(pwd)"
  zip -r ${package_name}.zip python  # zip contents of python to zip name
  cd ../../ # go back out to scripts dir
done

cd $CWD  # return to original location

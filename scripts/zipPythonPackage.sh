#!/bin/bash
# This is a script to download a python package binaries and zip it
# The intention is to use that package as a layer for a lambda function (or something else).
# use: 
#   sh zipPythonPackage.sh -p praw -s [bucket name]
# based on https://www.linkedin.com/pulse/add-external-python-libraries-aws-lambda-using-layers-gabe-olokun/
# Note: an old version of this script also moved the zip file to s3, this functionality has been removed.
# you may need to run chmod +x ./zipPythonPackage.sh

set -e

while getopts p:s: flag
do
    case "${flag}" in
        p) package=${OPTARG};;  # ie praw==7.7.0
        s) s3_bucket=${OPTARG};;  # ie s3://your-s3-bucket-name/
    esac
done
: ${package:?Missing -p} ${s3_bucket:?Missing -s}  # checks if these have been set https://unix.stackexchange.com/questions/621004/bash-getopts-mandatory-arguments
echo "package: $package";
echo "S3 Location: s3://$s3_bucket";

SCRIPT_PATH=${0%/*}  # https://stackoverflow.com/questions/6393551/what-is-the-meaning-of-0-in-a-bash-script
CWD=${pwd}
cd $SCRIPT_PATH

mkdir -p ./zippedPythonPackages/${package}/python

cd ./zippedPythonPackages/${package}/python

# install binaries for package
pip install \
    --platform manylinux2014_x86_64 \
    --target=. \
    --implementation cp \
    --python 3.7 \
    --only-binary=:all: \
    --upgrade ${package}

rm -rf *dist-info  # some cleanup of unnecessary stuff
# zip package
cd ..
rm -rf ${package}.zip # remove first if it exists
zip -r ${package}.zip python  # zip contents of python to zip name

cd $CWD  # return to original location

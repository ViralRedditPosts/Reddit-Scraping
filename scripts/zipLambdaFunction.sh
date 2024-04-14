#!/bin/bash
# This is meant to zip a lambda function with the reddit config
# use: 
#   zipLambdaFunction.sh -f someFunction
# saves zip to zippedLambdaFunction/someFunction.zip
# you may need to run chmod +x ./zipLambdaFunction.sh

set -e

while getopts f: flag
do
    case "${flag}" in
        f) function_name=${OPTARG};;  # ie someFunction located in ../lambdaFunction/someFunction
    esac
done
: ${function_name:?Missing -f}   # checks if these have been set https://unix.stackexchange.com/questions/621004/bash-getopts-mandatory-arguments
echo "lambda function: $function_name";

SCRIPT_PATH=${0%/*}  # https://stackoverflow.com/questions/6393551/what-is-the-meaning-of-0-in-a-bash-script
CWD=${pwd}
cd $SCRIPT_PATH

[ -d "../lambdaFunctions/${function_name}" ] && echo "Directory ../lambdaFunctions/${function_name} exists." || { echo "Error: Directory ../lambdaFunctions/${function_name} does not exist."; exit 1; }

cd ./zippedLambdaFunction/
rm -r ./${function_name} || true
cp -r ../../lambdaFunctions/${function_name} ./  # copy lambda function files here
rm -rf ${function_name}.zip # remove first if it exists
cd ./${function_name}/  # for some reason you have to zip from within this folder or it wont work, it otherwise wraps it in another folder
#rm -rf ./*.ipynb*  # remove any notebook stuff
zip -r ../${function_name}.zip * -x "*.ipynb*" "*pycache*"    # zip of function 
cd ..
rm -r ./${function_name}  # clean up unzipped file

cd $CWD  # return to original place

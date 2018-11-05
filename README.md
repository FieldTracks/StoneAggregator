# StoneAggregator
This is a script that aggregates sensor data from stones for use by the frontend (fieldmon). It further provides functionality for logging sensor data to a mariadb database and also handles descriptions for stones (i.e. assigned names and colors from the frontend).

This repository is part of the [Fieldtracks](https://fieldtracks.org/) project, which aims at creating a tracking system to be used in field exercises by relief organizations.

## Setup
1) Clone the project: `git clone https://github.com/FieldTracks/StoneAggregator.git`
2) Switch to the project directory: `cd StoneAggregator`
3) Setup a virtual python environment: `python3 -m venv env`
4) Enter the virtual environment: `source env/bin/activate`
5) Install dependencies: `pip3 install -r requirements.txt`
6) Copy and edit the default config file: `cp config-localhost.ini config.ini`
7) Run the script: `./aggregator.py config.ini`

## Message format
You can find descriptions and examples of sensor messages and aggregated messages [here](https://github.com/FieldTracks/StoneAggregator/blob/master/EXAMPLE_MSGS.md).

## License
This file is part of StoneAggregator - (C) The Fieldtracks Project

    StoneAggregator is distributed under the civilian open source license (COSLi). Military usage is forbidden.

    You should have received a copy of COSLi along with StoneAggregator.
    If not, please contact info@fieldtracks.org

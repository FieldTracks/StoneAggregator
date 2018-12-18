#!/bin/sh

mkdir -p root/usr/local/bin
mkdir -p root/etc/stoneaggregator
mkdir -p root/usr/share/stoneaggregator

cp ../aggregation.py root/usr/local/bin/stoneaggregator
cp ../config-localhost.ini root/etc/stoneaggregator/config.ini
cp ../requirements.txt root/usr/share/stoneaggregator/

chmod go-rwx root/etc/stoneaggregator/config.ini

sed -i s/##BUILDNR##/${BUILD_NUMBER}/ root/DEBIAN/control

mv root stoneaggregator_1.0-${BUILD_NUMBER}

fakeroot dpkg-deb --build stoneaggregator_1.0-${BUILD_NUMBER}

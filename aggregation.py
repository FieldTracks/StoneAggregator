#!/usr/bin/env python3

import threading
import configparser
import sys
import json
import signal
import zlib
import ssl
from datetime import datetime
from dateutil import tz
import paho.mqtt.client as mqtt


class BeaconId:
    # Might be used as alternative for
    # beacon identification. Question
    # is if all devices provide a
    # unique, non-changing MAC address

    def __init__(self, uuid, major, minor):
        self.uuid = uuid
        self.major = major
        self.minor = minor

    def __eq__(self, other):
        return (self.uuid, self.major, self.minor) == (other.uuid, other.major, other.minor)

    def __hash__(self):
        return hash((self.uuid, self.major, self.minor))


class Contact:
    def __init__(self, timestamp, mac_address, b_address, rssi_min, rssi_max, rssi_avg, tx_rssi):
        self.timestamp = timestamp
        self.mac_address = mac_address
        self.b_address = b_address
        self.rssi_min = rssi_min
        self.rssi_max = rssi_max
        self.rssi_avg = rssi_avg
        self.tx_rssi = tx_rssi


class Stone:
    def __init__(self, mac_address, b_address, comment):
        # Static data
        self.mac_address = mac_address
        self.b_address = b_address
        self.comment = comment

        # Updates
        self.last_update = 0
        self.contacts = []

    def update(self, timestamp, recent_contacts):
        # We assume for now that updates are fairly recent
        # NOTE: This might change in the future if we
        # queue and send messages via LoRaWAN
        self.last_update = timestamp

        # Remove contacts that are older than 60 seconds
        self.contacts = [c for c in self.contacts if c.timestamp >= (timestamp - 60)]

        # Update or add new contacts
        for ct in recent_contacts:
            self.contacts = list(filter(lambda x : x.mac_address != ct.mac_address, self.contacts))
            self.contacts.append(ct)


class World:
    def __init__(self):
        self.stones = {} # Contains stones: mac => stone
        self.descs = {} # Contains descriptions for nodes: mac => (name, color)
        self.lock = threading.Lock()

    def get_lock(self):
        return self.lock

    def get_stones(self):
        return self.stones

    def get_descs(self):
        return self.descs

    def update_stone(self, stone):
        with self.get_lock():
            if stone.mac_address not in self.stones:
                self.stones[stone.mac_address] = stone
            else:
                self.stones[stone.mac_address].update(stone.last_update, stone.contacts)

    def update_desc(self, mac_address, name, color):
        with self.get_lock():
            self.descs[mac_address] = (name, color)


class Aggregator:
    @staticmethod
    def aggregate_stones(stones):
        # Create list of stones
        stones_info = dict()
        for mac, s in stones.items():
            stones_info[mac] = {'uuid': s.b_address.uuid, 'major': s.b_address.major, 'minor': s.b_address.minor, 'comment': s.comment, 'last_seen': s.last_update}
            if CONFIG.getboolean('Aggregator', 'StoneInfoIncludeContacts', fallback=True):
                stones_info[mac]['contacts'] = list()
                for c in s.contacts:
                    stones_info[mac]['contacts'].append({'mac': c.mac_address, 'uuid': c.b_address.uuid, 'major': c.b_address.major, 'minor': c.b_address.minor, 'rssi_avg': c.rssi_avg, 'rssi_tx': c.tx_rssi})
        return json.dumps(stones_info)

    @staticmethod
    def aggregate_graph(stones, current_time):
        # Create list of stones
        stones_info = dict()
        for mac, s in stones.items():
            stones_info[mac] = {'uuid': s.b_address.uuid, 'major': s.b_address.major, 'minor': s.b_address.minor, 'comment': s.comment, 'age': current_time - s.last_update, 'contacts': []}
            for c in s.contacts:
                stones_info[mac]['contacts'].append({'mac': c.mac_address, 'uuid': c.b_address.uuid, 'major': c.b_address.major, 'minor': c.b_address.minor, 'age': current_time - c.timestamp, 'rssi_avg': c.rssi_avg, 'rssi_tx': c.tx_rssi})
        return json.dumps(stones_info)

    @staticmethod
    def aggregate_descs(descriptions):
        # Create list of descriptions
        descs_info = dict()
        for mac in descriptions:
            descs_info[mac] = {'name': descriptions[mac][0], 'color': descriptions[mac][1]}
        return json.dumps(descs_info)


class MqttService:
    def __init__(self, world):
        self.world = world

        host = CONFIG.get('MQTT Auth', 'Hostname', fallback='127.0.0.1')
        port = CONFIG.getint('MQTT Auth', 'Port', fallback=1883)
        usetls = CONFIG.getboolean('MQTT Auth', 'UseTLS', fallback=False)
        cacert = CONFIG.get('MQTT Auth', 'CACert', fallback='server.pem')
        user = CONFIG.get('MQTT Auth', 'Username', fallback='Aggregator')
        passwd = CONFIG.get('MQTT Auth', 'Password', fallback='')

        self.channel_in_sensors_prefix = CONFIG.get('MQTT Channels', 'ChannelPrefixSensors', fallback='JellingStone/')
        self.channel_in_sensors = self.channel_in_sensors_prefix + '+'
        self.channel_in_nameupdate = CONFIG.get('MQTT Channels', 'ChannelNameUpdates', fallback='NameUpdate')
        self.channel_out_stones = CONFIG.get('MQTT Channels', 'ChannelStoneInfo', fallback='Aggregated/Stones')
        self.channel_out_graph = CONFIG.get('MQTT Channels', 'ChannelGraphInfo', fallback='Aggregated/Graph')
        self.channel_out_names = CONFIG.get('MQTT Channels', 'ChannelNames', fallback='Aggregated/Names')

        self.client = mqtt.Client('Aggregator')
        self.client.username_pw_set(user, passwd)
        self.client.on_message = self.on_message
        if usetls:
            self.client.tls_set(cacert, tls_version=ssl.PROTOCOL_TLSv1_2)
        self.client.connect(host, port)
        self.client.subscribe(self.channel_in_sensors)
        self.client.subscribe(self.channel_in_nameupdate)

        self.update_interval = CONFIG.getint('Aggregator', 'UpdateInterval', fallback=4)
        self.last_stone_update = 0


    def watch_mqtt(self):
        self.client.loop_forever()

    def stop(self):
        self.client.disconnect()

    def on_message(self, client, userdata, message):
        topic = message.topic
        payload = message.payload

        try:
            # Check for zlib header and decompress if neccessary
            if payload[0] == 0x78 and payload[1] == 0x9c:
                payload = zlib.decompress(payload)

            # Get data from json
            data = json.loads(payload.decode('utf-8'))
        except Exception as e:
            print('Could not decode message of length {} in topic {}'.format(len(payload), topic))
            return

        if topic.startswith(self.channel_in_sensors_prefix):
            # Parse data into Stone object
            mac_address = topic[len(self.channel_in_sensors_prefix):]
            stone = Stone(mac_address, BeaconId(data['uuid'], data['major'], data['minor']), data['comment'])

            # Parse time string (time is handeled in UTC)
            time_string = data['timestamp']
            time_dt = datetime.strptime(time_string, '%Y-%m-%dT%H:%M:%SZ')
            time_dt.replace(tzinfo=tz.UTC)
            timestamp = int(time_dt.timestamp())

            # Add contacts
            contacts = list()
            for ct in data['data']:
                bid = BeaconId(ct['uuid'], ct['major'], ct['minor']) if ('uuid' in ct and 'major' in ct and 'minor' in ct) else BeaconId('', 0, 0)
                contacts.append(Contact(timestamp, ct['mac'], bid, ct['min'], ct['max'], ct['avg'], ct['remoteRssi']))
            stone.update(timestamp, contacts)

            # Update world model
            self.world.update_stone(stone)

            # Publish aggregated data
            if (timestamp - self.last_stone_update) >= self.update_interval:
                self.last_stone_update = timestamp
                with self.world.get_lock():
                    agg_stones = Aggregator.aggregate_stones(self.world.get_stones())
                    agg_graph = Aggregator.aggregate_graph(self.world.get_stones(), timestamp)
                self.publish_persistent(self.channel_out_stones, agg_stones.encode('utf-8'))
                self.publish_persistent(self.channel_out_graph, agg_graph.encode('utf-8'))

        elif topic == self.channel_in_nameupdate:
            # Update the description
            self.world.update_desc(data['mac'], data['name'], data['color'])

            # Compose and pin a new message with all names
            with self.world.get_lock():
                agg_descs = Aggregator.aggregate_descs(self.world.get_descs())
            self.publish_persistent(self.channel_out_names, agg_descs.encode('utf-8'))


    def publish_persistent(self, topic, payload):
        self.client.publish(topic, payload, retain=True)


class Main:
    def __init__(self):
        if len(sys.argv) != 2:
            print('Usage: {} <config file>'.format(sys.argv[0]))
            exit(1)

        # Won't check for now if the config file is valid
        # Falls back to default values if options are missing
        global CONFIG
        CONFIG = configparser.ConfigParser()
        CONFIG.read(sys.argv[1])

        # Create a world for storing data
        self.world = World()

        # Setup the MQTT service for communication
        print('Starting MQTT service...')
        self.mqtts = MqttService(self.world)

        # Catch sigints
        signal.signal(signal.SIGINT, self.catch_sigint)

        # Listen for incoming mqtt data (blocking)
        print('Running...')
        self.mqtts.watch_mqtt()
        print('Done!')


    def catch_sigint(self, signum, frame):
        print('\rInterrupted!')
        print('Stopping...')
        self.mqtts.stop()


if __name__ == '__main__':
    Main()
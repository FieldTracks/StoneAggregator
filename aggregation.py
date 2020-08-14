#!/usr/bin/env python3

import logging
import logging.handlers
import threading
import configparser
import sys
import json
import signal
import zlib
import ssl
import time
from datetime import datetime, timezone
import paho.mqtt.client as mqtt
from sqlalchemy import create_engine, ForeignKey, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship


class Utils:
    def iso_to_tstamp(iso_time):
        # Parse time string (time is handled in UTC)
        time_iso = iso_time
        time_dt = datetime.strptime(time_iso, '%Y-%m-%dT%H:%M:%SZ')
        time_dt = time_dt.replace(tzinfo=timezone.utc)
        timestamp = int(time_dt.timestamp())
        return timestamp


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
        self.last_update = ''
        self.contacts = []

    def update(self, iso_time, recent_contacts):
        # We assume for now that updates are fairly recent
        # NOTE: This might change in the future if we
        # queue and send messages via LoRaWAN
        self.last_update = iso_time
        timestamp = Utils.iso_to_tstamp(iso_time)

        # Remove contacts that are older than 60 seconds
        self.contacts = [c for c in self.contacts if Utils.iso_to_tstamp(c.timestamp) >= (timestamp - 60)]

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
            stones_info[mac] = {'uuid': s.b_address.uuid, 'major': s.b_address.major, 'minor': s.b_address.minor, 'comment': s.comment, 'timestamp': s.last_update}
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
            stones_info[mac] = {'uuid': s.b_address.uuid, 'major': s.b_address.major, 'minor': s.b_address.minor, 'comment': s.comment, 'age': current_time - Utils.iso_to_tstamp(s.last_update), 'contacts': []}
            for c in s.contacts:
                stones_info[mac]['contacts'].append({'mac': c.mac_address, 'uuid': c.b_address.uuid, 'major': c.b_address.major, 'minor': c.b_address.minor, 'age': current_time - Utils.iso_to_tstamp(c.timestamp), 'rssi_avg': c.rssi_avg, 'rssi_tx': c.tx_rssi})
        return json.dumps(stones_info)

    @staticmethod
    def aggregate_descs(descriptions):
        # Create list of descriptions
        descs_info = dict()
        for mac in descriptions:
            descs_info[mac] = {'name': descriptions[mac][0], 'color': descriptions[mac][1]}
        return json.dumps(descs_info)


class MqttService:
    def __init__(self, world, dbs):
        self.world = world
        self.dbs = dbs
        self.is_running = True

        host = CONFIG.get('MQTT Auth', 'Hostname', fallback='127.0.0.1')
        port = CONFIG.getint('MQTT Auth', 'Port', fallback=1883)
        usetls = CONFIG.getboolean('MQTT Auth', 'UseTLS', fallback=False)
        cacert = CONFIG.get('MQTT Auth', 'CACert', fallback='server.pem')
        insecure = CONFIG.getboolean('MQTT Auth', 'Insecure', fallback=False)
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
        if usetls:
            self.client.tls_set(cacert, tls_version=ssl.PROTOCOL_TLSv1_2)
            if insecure:
                self.client.tls_insecure_set(True)
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)

        self.client.on_message = self.on_message
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.connect(host, port)

        self.update_interval = CONFIG.getint('Aggregator', 'UpdateInterval', fallback=4)
        self.last_stone_update = 0


    def watch_mqtt(self):
        self.client.loop_forever()

    def stop(self):
        self.is_running = False
        self.client.disconnect()

    def on_connect(self, client, userdata, flags, rc):
        self.client.subscribe(self.channel_in_sensors)
        self.client.subscribe(self.channel_in_nameupdate)
        self.client.subscribe(self.channel_out_names)
        logging.info('MQTT connected!')

    def on_disconnect(self, client, userdata, rc):
        if self.is_running and rc != mqtt.MQTT_ERR_SUCCESS:
            logging.warning('Lost connection to the MQTT broker!')
        else:
            logging.info('MQTT disconnected!')

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
            logging.warning('Could not decode message of length {} in topic {}'.format(len(payload), topic))
            return

        if topic.startswith(self.channel_in_sensors_prefix):
            # Parse data into Stone object
            mac_address = topic[len(self.channel_in_sensors_prefix):]
            stone = Stone(mac_address, BeaconId(data['uuid'], data['major'], data['minor']), data['comment'])

            # Add contacts
            contacts = list()
            for ct in data['data']:
                bid = BeaconId(ct['uuid'], ct['major'], ct['minor']) if ('uuid' in ct and 'major' in ct and 'minor' in ct) else BeaconId('', 0, 0)
                contacts.append(Contact(data['timestamp'], ct['mac'], bid, ct['min'], ct['max'], ct['avg'], ct['remoteRssi']))
            stone.update(data['timestamp'], contacts)

            # Update world model
            self.world.update_stone(stone)

            # Publish aggregated data
            if(time.time() - self.last_stone_update) >= self.update_interval:
                self.last_stone_update = time.time()
                with self.world.get_lock():
                    agg_stones = Aggregator.aggregate_stones(self.world.get_stones())
                    agg_graph = Aggregator.aggregate_graph(self.world.get_stones(), Utils.iso_to_tstamp(data['timestamp']))
                self.publish_persistent(self.channel_out_stones, agg_stones.encode('utf-8'))
                self.publish_persistent(self.channel_out_graph, agg_graph.encode('utf-8'))

            # Store stone event in database
            if self.dbs is not None:
                self.dbs.store_event(stone)

        elif topic == self.channel_in_nameupdate:
            # Update the description
            self.world.update_desc(data['mac'], data['name'], data['color'])

            # Compose and pin a new message with all names
            with self.world.get_lock():
                agg_descs = Aggregator.aggregate_descs(self.world.get_descs())
            self.publish_persistent(self.channel_out_names, agg_descs.encode('utf-8'))

        elif topic == self.channel_out_names:
            # This should pick up the last retained aggregated names on startup
            # Since we only need the last message we should unsubscribe here
            self.client.unsubscribe(self.channel_out_names)

            if type(data) is not dict:
                logging.warning('Can\'t parse retained names!')
                return

            num_imported = 0

            for mac, entry in data.items():
                if type(entry) is dict and 'name' in entry and 'color' in entry:
                    self.world.update_desc(mac, entry['name'], entry['color'])
                    num_imported += 1
                else:
                    logging.warning('Invalid name entry in retained message!')

            logging.info('Imported {} descriptions from last aggregated message'.format(num_imported))


    def publish_persistent(self, topic, payload):
        self.client.publish(topic, payload, retain=True)


class DBService:
    Base = declarative_base()

    class SensorContact(Base):
        __tablename__ = 'sensor_contacts'

        id = Column(Integer, primary_key=True, autoincrement=True)
        stone_event_id = Column(Integer, ForeignKey('stone_events.id'))
        mac = Column(String(17))
        uuid = Column(String(47))
        major = Column(Integer)
        minor = Column(Integer)
        min = Column(Integer)
        max = Column(Integer)
        avg = Column(Integer)
        remote_rssi = Column(Integer)

        stone_event = relationship('StoneEvent', back_populates='contacts')

    class StoneEvent(Base):
        __tablename__ = 'stone_events'

        id = Column(Integer, primary_key=True, autoincrement=True)
        mac = Column(String(17))
        uuid = Column(String(47))
        major = Column(Integer)
        minor = Column(Integer)
        timestamp = Column(DateTime)
        comment = Column(String(128))

        contacts = relationship('SensorContact', back_populates='stone_event')

    def __init__(self):
        host = CONFIG.get('Database', 'Hostname', fallback='localhost')
        port = CONFIG.getint('Database', 'Port', fallback=3306)
        user = CONFIG.get('Database', 'Username', fallback='aggregator')
        passwd = CONFIG.get('Database', 'Password', fallback='')
        db = CONFIG.get('Database', 'Database', fallback='fieldtracks')

        self.engine = create_engine('mysql+mysqldb://{}:{}@{}:{}/{}'.format(user, passwd, host, port, db))
        DBService.Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()

    def stop(self):
        self.session.close()

    def store_event(self, stone):
        time = datetime.utcfromtimestamp(stone.last_update)
        db_stone = DBService.StoneEvent(mac=stone.mac_address,
                                        uuid=stone.b_address.uuid,
                                        major=stone.b_address.major,
                                        minor=stone.b_address.minor,
                                        timestamp=time,
                                        comment=stone.comment)
        for contact in stone.contacts:
            db_contact = DBService.SensorContact(mac=contact.mac_address,
                                                 uuid=contact.b_address.uuid,
                                                 major=contact.b_address.major,
                                                 minor=contact.b_address.minor,
                                                 min=contact.rssi_min,
                                                 max=contact.rssi_max,
                                                 avg=contact.rssi_avg,
                                                 remote_rssi=contact.tx_rssi)
            db_stone.contacts.append(db_contact)

        self.session.add(db_stone)
        self.session.commit()


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

        # Configure logging
        logging.basicConfig(
            format='%(asctime)s.%(msecs)03d %(levelname)s %(name)s %(message)s',
            level=logging.NOTSET,
            datefmt='%s %Y-%m-%d %H:%M:%S')

        # Create a world for storing data
        self.world = World()

        # Setup database
        if CONFIG.getboolean('Database', 'EnableLogging', fallback=False):
            logging.info('Setting up database...')
            self.dbs = DBService()
        else:
            self.dbs = None

        # Setup the MQTT service for communication
        logging.info('Starting MQTT service...')
        self.mqtts = MqttService(self.world, self.dbs)

        # Catch sigints
        signal.signal(signal.SIGINT, self.catch_sigint)

        # Listen for incoming mqtt data (blocking)
        logging.info('Running...')
        self.mqtts.watch_mqtt()
        logging.info('Done!')


    def catch_sigint(self, signum, frame):
        logging.info('\rInterrupted!')
        logging.info('Stopping...')
        self.mqtts.stop()
        if self.dbs is not None:
            self.dbs.stop()


if __name__ == '__main__':
    Main()

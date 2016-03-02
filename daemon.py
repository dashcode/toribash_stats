#! /usr/bin/python3

import functools
import logging
import operator
import requests
import socket
import time

from model import db, User, Stat

logger = logging.getLogger('daemon')
logger.setLevel(logging.DEBUG)

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

def get_clients():
    clients = []

    sock = socket.socket()
    sock.connect(("144.76.163.135", 22000))

    _buffer = ''
    while True:
        _buffer = _buffer + sock.recv(4096).decode('utf-8', 'ignore')
        if not _buffer:
            break
        temp = _buffer.split('\n')
        _buffer = temp.pop()
        for line in temp:
            args = line.split(';', 1)
            if len(args) < 2:
                continue
            cmd, args = args
            args = args.strip()
            if cmd == 'SERVER 0':
                ip_port, room = args.split(' ', 1)
                ip, port = ip_port.split(':')
            elif cmd == 'CLIENTS 2':
                for client in args.strip().split():
                    username = (client
                                .split(']')[-1].strip()
                                .split(')')[-1].strip())

                    if not username:
                        continue

                    clients.append({
                        'username': username,
                        'room': room,
                        'ip': ip,
                        'port': port
                    })

    sock.close()
    return clients

chunkify = lambda l, n: (l[i:i+n] for i in range(0, len(l), n))

BASE_URL = 'http://forum.toribash.com/'
UPDATE_CYCLE = 5 * 60

def main():
    #@functools.lru_cache(maxsize=65536)
    def get_user(username):
        user = User.query.filter_by(username=username).first()

        if user is None:
            user = User(username)
            db.session.add(user)

        return user

    while True:
        loop_start = time.monotonic()

        logger.info('Downloading client list')
        clients = get_clients()
        usernames = list(set(client['username'] for client in clients))
        pages = len(usernames) / 15
        queries = []

        for page, users_chunk in enumerate(chunkify(usernames, 15)):
            logger.info('Downloading user stats %i/%i', page, pages)
            for i in range(5):
                try:
                    users_info = requests.get(BASE_URL + 'tori_stats.php', params={
                        'format': 'json',
                        'username': ','.join(users_chunk)
                    }).json()
                    break
                except Exception:
                    time.sleep(2 ** i)
            else:
                continue

            if type(users_info) is not list:
                users_info = [users_info]

            for user_info in users_info:
                db.session.add(Stat(get_user(user_info['username']),
                                    user_info['tc'],
                                    user_info['qi']))

            db.session.commit()

        loop_length = time.monotonic() - loop_start
        sleep_time = max(0, UPDATE_CYCLE - loop_length)

        logger.info('Loop took %.2f seconds, sleeping for %.2f seconds',
                    loop_length, sleep_time)

        time.sleep(sleep_time)

if __name__ == '__main__':
    main()

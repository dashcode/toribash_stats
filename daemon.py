#! /usr/bin/python3

import json
import logging
import requests
import socket
import time

import MySQLdb
import MySQLdb.cursors

config = json.load(open('config.json'))

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
    db = MySQLdb.connect(**config['db'])
    cursor = db.cursor(MySQLdb.cursors.DictCursor)

    while True:
        loop_start = time.monotonic()

        logger.info('Downloading client list')
        clients = get_clients()
        usernames = list(set(client['username'].lower() for client in clients))
        pages = len(usernames) / 15
        queries = []

        for page, users_chunk in enumerate(chunkify(usernames, 15)):
            logger.info('Downloading user stats %i/%i', page, pages)
            for i in range(5):
                try:
                    users_info = requests.get(BASE_URL + 'tori_stats.php', params={
                        'format': 'json',
                        'username': ','.join(users_chunk)
                    }, timeout=30).json()
                    break
                except Exception:
                    time.sleep(2 ** i)
            else:
                continue

            if type(users_info) is not list:
                users_info = [users_info]

            for user_info in users_info:
                cursor.execute("SELECT * FROM user WHERE username=%s", (user_info['username'],))
                user = cursor.fetchone()

                if user is None:
                    cursor.execute("""
                        INSERT INTO user
                        (username, current_tc, current_qi, current_winratio,
                         current_elo, current_posts, current_achiev_progress)
                        VALUES(%s, %s, %s, %s, %s, %s, %s)
                    """, (user_info['username'], user_info['tc'],
                          user_info['qi'], user_info['winratio'],
                          user_info['elo'], user_info['posts']))

                    user_id = cursor.lastrowid
                else:
                    cursor.execute("""
                        UPDATE user SET
                        current_tc=%s, current_qi=%s, current_winratio=%s,
                        current_elo=%s, current_posts=%s, current_achiev_progress=%s
                        WHERE id=%s
                    """, (user_info['tc'], user_info['qi'], user_info['winratio'],
                          user_info['elo'], user_info['posts'], user['id']))
                    user_id = user['id']

                try:
                    cursor.execute("""
                        INSERT INTO stat
                        (user_id, tc, qi, time, winratio, elo, posts)
                        VALUES(%s, %s, %s, UTC_TIMESTAMP(), %s, %s, %s, %s)
                    """, (user_id, user_info['tc'], user_info['qi'],
                        user_info['winratio'], user_info['elo'],
                        user_info['posts']))
                except MySQLdb.Error:
                    # Most probably a duplicate key
                    pass

            db.commit()

        loop_length = time.monotonic() - loop_start
        sleep_time = max(0, UPDATE_CYCLE - loop_length)

        logger.info('Loop took %.2f seconds, sleeping for %.2f seconds',
                    loop_length, sleep_time)

        time.sleep(sleep_time)

if __name__ == '__main__':
    main()

#! /usr/bin/python3

import hashlib
import json
import logging
import socket
import time

from bs4 import BeautifulSoup
import requests

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

BASE_URL = 'http://forum.toribash.com/'
UPDATE_CYCLE = 15 * 60


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


def get_forum_clients():
    session = requests.session()

    password_hash = hashlib.md5(
        config['account']['password'].encode()).hexdigest()

    session.post(BASE_URL + 'login.php?do=login', {
        'vb_login_username':        config['account']['username'],
        'vb_login_password':        '',
        'vb_login_md5password':     password_hash,
        'vb_login_md5password_utf': password_hash,

        'cookieuser': 1,  # Stay logged in
        'do': 'login',
        's': '',
        'securitytoken': 'guest'
    })

    soup = BeautifulSoup(session.get(BASE_URL).text, 'html.parser')
    users = (soup.find(id='collapseobj_forumhome_activeusers')
             .find_all('div')[2]
             .find_all('a'))

    return [user.text for user in users]


def main():
    db = MySQLdb.connect(**config['db'])
    cursor = db.cursor(MySQLdb.cursors.DictCursor)

    while True:
        loop_start = time.monotonic()

        logger.info('Downloading client list')

        try:
            ingame_clients = set(c['username'].lower() for c in get_clients())
            forum_clients = set(c.lower() for c in get_forum_clients())
            usernames = ingame_clients | forum_clients
        except Exception:
            time.sleep(30)
            continue

        cursor.execute("""
            INSERT INTO online_user
            (users_ingame, users_forum, time)
            VALUES(%s, %s, UTC_TIMESTAMP())
        """, (len(ingame_clients), len(forum_clients)))

        db.commit()

        for i, user in enumerate(usernames, start=1):
            logger.info("Downloading %s's stats %i/%i",
                        user, i, len(usernames))

            for i in range(5):
                try:
                    user_info = requests.get(
                        BASE_URL + 'tori_stats.php',
                        params={
                            'format': 'json',
                            'username': user
                        }, timeout=30).json()
                    break
                except ValueError:
                    break
                except Exception:
                    time.sleep(2 ** i)
            else:
                continue

            if user_info['qi'] == 0:
                continue

            tc = user_info['tc'] or 0
            winratio = user_info['winratio'] or 0.0
            elo = user_info['elo'] or 1600

            cursor.execute("""
                INSERT INTO user
                (username, current_tc, current_qi, current_winratio,
                 current_elo, current_posts)
                VALUES(%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    current_tc=VALUES(current_tc),
                    current_qi=VALUES(current_qi),
                    current_winratio=VALUES(current_winratio),
                    current_elo=VALUES(current_elo),
                    current_posts=VALUES(current_posts)
            """, (user_info['username'], tc, user_info['qi'],
                  winratio, elo, user_info['posts']))

            try:
                cursor.execute("""
                    INSERT INTO stat
                    (user_id, tc, qi, time, winratio, elo, posts)
                    VALUES((SELECT id FROM user WHERE username=%s),
                           %s, %s, UTC_TIMESTAMP(), %s, %s, %s)
                """, (user_info['username'], tc, user_info['qi'], winratio,
                      elo, user_info['posts']))
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

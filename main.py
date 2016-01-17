#! /usr/bin/python3

from tornado.wsgi import WSGIContainer
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.log import enable_pretty_logging
import tornado.options

from flask import (Flask, abort, render_template, g, flash, redirect, request,
                   url_for)
from flask.ext.cache import Cache

import MySQLdb
import MySQLdb.cursors

from collections import OrderedDict
import datetime
import json
import os

#from model import db, User, Stat

app = Flask(__name__)
app.secret_key = os.urandom(32)

cache = Cache(app, config={'CACHE_TYPE': 'simple'})

config = json.load(open('config.json'))

periods = OrderedDict([
    #('hourly',             60 * 60),
    ('daily',         24 * 60 * 60),
    ('weekly',    7 * 24 * 60 * 60),
    #('monthly',  30 * 24 * 60 * 60),
    #('yearly',  365 * 24 * 60 * 60)
])

@app.before_request
def before_request():
    g.db = MySQLdb.connect(**config['db'])
    g.cursor = g.db.cursor(MySQLdb.cursors.DictCursor)

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.route('/')
@cache.cached(timeout=5 * 60)
def index():
    top_tc = []
    top_qi = []
    top_tc_spenders = []

    #g.cursor.execute("SET profiling_history_size = 100")
    #g.cursor.execute("SET profiling = 1")

    for tc_qi, top_list, order, ifnull in (('tc', top_tc, 'ASC', 2**32-1), ('qi', top_qi, 'ASC', 2**32-1), ('tc', top_tc_spenders, 'DESC', 0)):
        for period, period_length in periods.items():
            g.cursor.execute("""
                SELECT *
                FROM stat as stat2
                JOIN user ON id=user_id
                GROUP BY user_id
                ORDER BY IFNULL((
                    SELECT {0} 
                    FROM stat
                    WHERE user_id=stat2.user_id AND UNIX_TIMESTAMP(time) > UNIX_TIMESTAMP() - %s
                    ORDER BY time ASC
                    LIMIT 1
                ), {2}) - (
                    SELECT {0}
                    FROM stat
                    WHERE user_id=stat2.user_id
                    ORDER BY time DESC
                    LIMIT 1
                ) {1}
                LIMIT 10;""".format(tc_qi, order, ifnull), (period_length,))

            period_earnings = []
            for user in g.cursor.fetchall():
                #g.cursor.execute("SET profiling = 0")
                g.cursor.execute("""
                    SELECT {} as amount
                    FROM stat
                    WHERE user_id=%s AND UNIX_TIMESTAMP(time) > UNIX_TIMESTAMP() - %s
                    ORDER BY time ASC
                """.format(tc_qi), (user['id'], period_length))

                old_amount = g.cursor.fetchone()

                if not old_amount:
                    continue

                g.cursor.execute("""
                    SELECT {} as amount
                    FROM stat
                    WHERE user_id=%s
                    ORDER BY time DESC
                """.format(tc_qi), (user['id'],))

                current_amount = g.cursor.fetchone()

                if not current_amount:
                    continue

                period_earnings.append({
                    'username': user['username'],
                    tc_qi: old_amount['amount'],
                    'current_' + tc_qi: current_amount['amount']
                })
            #g.cursor.execute("SET profiling = 1")
            top_list.append((period, period_earnings))

    top_tc_all = []
    top_qi_all = []

    for tc_qi, top_result in (('tc', top_tc_all), ('qi', top_qi_all)):
        g.cursor.execute("""
            SELECT {0}, user.username as username
            FROM stat as stat1
            JOIN user ON user.id = stat1.user_id
            WHERE stat1.time = (
                SELECT MAX(stat2.time)
                FROM stat as stat2
                WHERE stat1.user_id = stat2.user_id
            )
            ORDER BY {0} DESC
            LIMIT 10
        """.format(tc_qi))

        top_result.extend(g.cursor.fetchall())

    #g.cursor.execute("SHOW PROFILES")

    #import pprint
    #pprint.pprint(g.cursor.fetchall())

    return render_template('index.html',
                           top_tc=top_tc,
                           top_qi=top_qi,
                           top_tc_spenders=top_tc_spenders,
                           top_tc_all=top_tc_all,
                           top_qi_all=top_qi_all)

@app.route('/stats/<username>')
@cache.cached(timeout=5 * 60)
def stats(username):
    g.cursor.execute("SELECT * FROM user WHERE username=%s", (username,))
    user = g.cursor.fetchone()

    if not user:
        abort(404)

    g.cursor.execute("SELECT * FROM stat WHERE user_id=%s", (user['id'],))
    stats = g.cursor.fetchall()

    return render_template('stats.html',
                           user=user,
                           stats=stats,
                           charttype='LineChart',
                           periods=periods.keys())

@app.route('/stats/<username>/<period>')
@cache.cached(timeout=5 * 60)
def stats_diff(username, period):
    def diff(it):
        prev = next(it)
        for e in it:
            yield e - prev
            prev = e
    if period not in periods:
        abort(404)

    g.cursor.execute("SELECT * FROM user WHERE username=%s", (username,))
    user = g.cursor.fetchone()

    g.cursor.execute("""
        SELECT *
        FROM stat
        WHERE user_id=%s
        GROUP BY UNIX_TIMESTAMP(time) DIV %s
    """, (user['id'], periods[period]))

    stats = g.cursor.fetchall()

    time = (s['time'] for s in stats)
    tc = diff(s['tc'] for s in stats)
    qi = diff(s['qi'] for s in stats)

    stats = ({'time': time_, 'tc': tc_, 'qi': qi_} for time_, tc_, qi_ in zip(time, tc, qi))

    return render_template('stats.html',
                           user=user,
                           stats=stats,
                           charttype='ColumnChart',
                           periods=periods.keys())

@app.route('/online_users')
@cache.cached(timeout=5 * 60)
def online_users():
    g.cursor.execute("""
        SELECT COUNT(user_id) as online, time
        FROM stat
        GROUP BY UNIX_TIMESTAMP(time) DIV 300
    """)
    online_users = g.cursor.fetchall()

    return render_template('online_users.html', online_users=online_users)

if __name__ == '__main__':
    enable_pretty_logging()
    tornado.options.options.log_file_prefix = 'access.log'
    tornado.options.parse_command_line()

    http_server = HTTPServer(WSGIContainer(app))
    http_server.listen(5001)
    IOLoop.instance().start()

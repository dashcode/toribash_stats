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

periods_length = OrderedDict([
    ('last_day',        24 * 60 * 60),
    ('last_month', 30 * 24 * 60 * 60)
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
    top_posts = []
    top_tc_spenders = []

    top_query_data = [
        ('tc',    top_tc,          'ASC'),
        ('qi',    top_qi,          'ASC'),
        ('posts', top_posts,       'ASC'),
        ('tc',    top_tc_spenders, 'DESC')
    ]

    for period, period_length in periods.items():
        g.cursor.execute("""
            CREATE TEMPORARY TABLE IF NOT EXISTS ranking_{0} AS (
                SELECT user.*, stat.*
                FROM user
                INNER JOIN stat
                    ON user.id = stat.user_id
                INNER JOIN (
                    SELECT user_id, MIN(time) time
                    FROM stat
                    WHERE UNIX_TIMESTAMP(time) > UNIX_TIMESTAMP() - %s
                    GROUP BY user_id
                ) b ON b.user_id = stat.user_id AND
                       b.time = stat.time
            )
        """.format(period), (period_length,))

        for stat, top_list, order in top_query_data:
            g.cursor.execute("""
                SELECT *
                FROM ranking_{0}
                ORDER BY {1} - current_{1} {2}
                LIMIT 25
            """.format(period, stat, order))

            top_list.append((period, g.cursor.fetchall()))

    all_tops = [
        ('tc',       '',                        'tc',        []),
        ('qi',       '',                        'qi',        []),
        ('posts',    '',                        'posters',   []),
        ('winratio', 'WHERE current_qi >= 500', 'win ratio', [])
    ]

    for stat, where, _, top_list in all_tops:
        g.cursor.execute("""
            SELECT current_{0} as {0}, username
            FROM user
            {1}
            ORDER BY current_{0} DESC
            LIMIT 25
        """.format(stat, where))
        top_list.extend(g.cursor.fetchall())

    return render_template('index.html',
                           top_tc=top_tc,
                           top_qi=top_qi,
                           top_posts=top_posts,
                           top_tc_spenders=top_tc_spenders,
                           all_tops=all_tops)


@app.route('/stats/<username>')
@cache.cached(timeout=5 * 60)
def stats(username):
    g.cursor.execute("SELECT * FROM user WHERE username=%s", (username,))
    user = g.cursor.fetchone()

    if not user:
        abort(404)

    g.cursor.execute("SELECT * FROM stat WHERE user_id=%s", (user['id'],))
    stats = g.cursor.fetchall()

    return render_template(
        'stats.html',
        user=user,
        stats=stats,
        charttype='LineChart',
        periods=list(periods.keys()) + list(periods_length.keys()))


@app.route('/stats/<username>/<period>')
@cache.cached(timeout=5 * 60)
def stats_diff(username, period):
    def diff(l):
        it = iter(l)
        prev = next(it)
        for e in it:
            yield e - prev
            prev = e

    if period not in periods and period not in periods_length:
        abort(404)

    g.cursor.execute("SELECT * FROM user WHERE username=%s", (username,))
    user = g.cursor.fetchone()

    if not user:
        abort(404)

    if period in periods:
        g.cursor.execute("""
            SELECT *
            FROM stat
            WHERE user_id=%s
            GROUP BY UNIX_TIMESTAMP(time) DIV %s
        """, (user['id'], periods[period]))

        keys = ('tc', 'qi', 'winratio', 'posts')
        stats = g.cursor.fetchall()
        period_stats = [(s['time'] for s in stats)]

        for key in keys:
            period_stats.append(diff([s[key] for s in stats]))

        stats = (dict(zip(('time',) + keys, stat_l))
                 for stat_l in zip(*period_stats))

        charttype = 'ColumnChart'
    else:
        g.cursor.execute("""
            SELECT * FROM stat
            WHERE
                user_id=%s AND
                UNIX_TIMESTAMP(time) > UNIX_TIMESTAMP() - %s
        """, (user['id'], periods_length[period]))

        stats = g.cursor.fetchall()

        charttype = 'LineChart'

    return render_template(
        'stats.html',
        user=user,
        stats=stats,
        charttype=charttype,
        periods=list(periods.keys()) + list(periods_length.keys()))


@app.route('/online_users')
@cache.cached(timeout=5 * 60)
def online_users():
    g.cursor.execute("""
        SELECT *
        FROM online_user
    """)

    return render_template('online_users.html',
                           online_users=g.cursor.fetchall())


@app.route('/users')
@app.route('/users/<order_by>/<asc_desc>/<int:page>')
@cache.cached(timeout=5*60)
def users(order_by='username', asc_desc='asc', page=1):
    order_by_rows = OrderedDict([
        ('username', ('username', 'asc')),
        ('tc', ('current_tc', 'desc')),
        ('qi', ('current_qi', 'desc')),
        ('winratio', ('current_winratio', 'desc')),
        ('posts', ('current_posts', 'desc')),
    ])

    if order_by not in order_by_rows or asc_desc not in ('asc', 'desc'):
        abort(404)

    users_per_page = 100

    g.cursor.execute("""
        SELECT * FROM user
        ORDER BY {} {}
        LIMIT %s
        OFFSET %s
    """.format(order_by_rows[order_by][0], asc_desc),
        (users_per_page, (page - 1) * users_per_page))

    return render_template(
        'users.html', users=g.cursor.fetchall(), users_per_page=users_per_page,
        order_by_rows=[(k, v[1]) for k, v in order_by_rows.items()],
        order_by=order_by, asc_desc=asc_desc, page=page)


if __name__ == '__main__':
    enable_pretty_logging()
    tornado.options.options.log_file_prefix = 'access.log'
    tornado.options.parse_command_line()

    http_server = HTTPServer(WSGIContainer(app))
    http_server.listen(5001)
    IOLoop.instance().start()

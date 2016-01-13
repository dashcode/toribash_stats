#! /usr/bin/python3

from tornado.wsgi import WSGIContainer
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.log import enable_pretty_logging
import tornado.options

from flask import Flask, abort, render_template
from flask.ext.cache import Cache

from collections import OrderedDict
import datetime

from model import db, User, Stat

app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'simple'})

periods = OrderedDict([
    ('hourly',             60 * 60),
    ('daily',         24 * 60 * 60),
    ('weekly',    7 * 24 * 60 * 60),
    ('monthly',  30 * 24 * 60 * 60),
    ('yearly',  365 * 24 * 60 * 60)
])

@app.route('/')
@cache.cached(timeout=60 * 30)
def index():
    top_tc = []
    top_qi = []

    for tc_qi, top_list in (('tc', top_tc), ('qi', top_qi)):
        for period, period_length in periods.items():
            result = db.engine.execute("""
                SELECT *
                FROM stat as stat2
                JOIN user ON id=user_id
                GROUP BY user_id
                ORDER BY (
                    SELECT {0} 
                    FROM stat
                    WHERE user_id=stat2.user_id AND UNIX_TIMESTAMP(time) > UNIX_TIMESTAMP() - ?
                    ORDER BY time ASC
                    LIMIT 1
                ) - (
                    SELECT {0}
                    FROM stat
                    WHERE user_id=stat2.user_id
                    ORDER BY time DESC
                    LIMIT 1
                ) ASC
                LIMIT 10;""".format(tc_qi), (period_length,))

            period_earnings = []
            for user in result:
                old_amount = db.engine.execute("""
                    SELECT {} as amount FROM stat
                    WHERE user_id=? AND UNIX_TIMESTAMP(time) > UNIX_TIMESTAMP() - ?
                    ORDER BY time ASC
                """.format(tc_qi), (user.id, period_length)).first()

                if not old_amount:
                    continue

                current_amount = db.engine.execute("""
                    SELECT {} as amount FROM stat
                    WHERE user_id=?
                    ORDER BY time DESC
                """.format(tc_qi), (user.id)).first()

                if not current_amount:
                    continue

                period_earnings.append({
                    'username': user.username,
                    tc_qi: old_amount.amount,
                    'current_' + tc_qi: current_amount.amount
                })
                print()
            print()

            top_list.append((period, period_earnings))

    return render_template('index.html', top_tc=top_tc, top_qi=top_qi)

@app.route('/stats/<username>')
def stats(username):
    user = User.query.filter_by(username=username).first_or_404()
    stats = Stat.query.filter_by(user=user)
    return render_template('stats.html', user=user, stats=stats, charttype='LineChart')

@app.route('/stats/<username>/<period>')
def stats_diff(username, period):
    def diff(it):
        prev = next(it)
        for e in it:
            yield e - prev
            prev = e
    if period not in periods:
        abort(404)

    user = User.query.filter_by(username=username).first_or_404()

    stats = db.engine.execute("""
        SELECT * FROM stat
        WHERE user_id=?
        GROUP BY UNIX_TIMESTAMP(time) DIV ?;
    """, (user.id, periods[period]))

    stats = list(stats)
    time = (s.time for s in stats)
    tc = diff(s.tc for s in stats)
    qi = diff(s.qi for s in stats)

    stats = ({'time': time_, 'tc': tc_, 'qi': qi_} for time_, tc_, qi_ in zip(time, tc, qi))

    return render_template('stats.html', user=user, stats=stats, charttype='ColumnChart')

if __name__ == '__main__':
    enable_pretty_logging()
    tornado.options.options.log_file_prefix = 'access.log'
    tornado.options.parse_command_line()

    http_server = HTTPServer(WSGIContainer(app))
    http_server.listen(5001)
    IOLoop.instance().start()

import itertools
import json

import MySQLdb
import MySQLdb.cursors


def with_previous(iterable, n=2):
    iterables = itertools.tee(iterable, n)
    for i, it in enumerate(iterables):
        for _ in range(i):
            next(it, None)
    return zip(*iterables)


config = json.load(open('config.json'))

db = MySQLdb.connect(**config['db'])
cursor = db.cursor(MySQLdb.cursors.DictCursor)

cursor.execute("""
    SELECT * FROM stat
    ORDER BY user_id, time ASC
""")

keys = ('tc', 'qi', 'winratio', 'elo', 'posts')
delete = []
for _, user_stats in itertools.groupby(cursor.fetchall(), lambda row: row['user_id']):
    for first, middle, last in with_previous(user_stats, 3):
        if all(first[key] == middle[key] == last[key] for key in keys):
            delete.append((middle['user_id'], middle['time']))

cursor.executemany("""
    DELETE FROM stat
    WHERE user_id = %s AND time = %s
""", delete)

db.commit()

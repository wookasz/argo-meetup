#! /usr/bin/env python

import datetime
import random
import uuid

# specify which schema and table to populate
schema = 'meetup'
table = 'events'

# template for insert DML statement
insert_tpl = 'insert into {} values (\'{}\', \'{}\', \'{}\', \'{}\');'

# parameters for generating data
n_sessions = 10
min_events_per_session = 1
max_events_per_session = 10
min_sec_between_events = 1
max_sec_between_events = 600
actions = ['message received', 'message sent']


# timedelta with random number of seconds
def rsecs():
    return datetime.timedelta(0, random.randint(min_sec_between_events, max_sec_between_events))


# helper to generate insert DML
def insert(id, sid, event_type, ts):
    print(insert_tpl.format(table, id, sid, event_type, ts))


# just creates a bunch of guids
def generate_sessions(n):
    sessions = []
    for i in range(n):
        sessions.append(uuid.uuid4())
    return sessions


# generates events for a sessions
def generate_session_events(sid, n_events):
    ts = datetime.datetime.utcnow() + rsecs()
    # always start with a message_received event
    events = [(uuid.uuid4(), actions[0], sid, ts)]
    for i in range(n_events - 2):
        ts = ts + rsecs()
        events.append((uuid.uuid4(), random.choice(actions), sid, ts))
    # always finish with a message_sent event
    if n_events > 1:
        ts = ts + rsecs()
        events.append((uuid.uuid4(), actions[-1], sid, ts))
    return events


def generate_events():
    events = []
    sessions = generate_sessions(n_sessions)
    for session in sessions:
        events += generate_session_events(session, random.randint(min_events_per_session, max_events_per_session))
    # sort events by timestamp so we have a nice timseries log
    events.sort(key=lambda tup: tup[3])
    return events


print('create schema if not exists {};'.format(schema))
print('set schema \'{}\';'.format(schema))
create_table_sql = """
create table if not exists {} (
    id text primary key not null,
    action text not null,
    sid text not null,
    timestamp timestamptz default now());
""".format(table)
print(create_table_sql)
for e in generate_events():
    insert(e[0], e[1], e[2], e[3])

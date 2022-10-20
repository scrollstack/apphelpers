import os
import requests
import time

import apphelpers.sessions as sessionslib

from converge import settings

base_url = 'http://127.0.0.1:5000/'
echo_url = base_url + 'echo'
secure_echo_url = base_url + 'secure-echo'
echo_groups_url = base_url + 'echo-groups'
pid_path = 'tests/run/app.pid'

sessiondb_conn = dict(host=settings.SESSIONSDB_HOST,
                      port=settings.SESSIONSDB_PORT,
                      password=settings.SESSIONSDB_PASSWD,
                      db=settings.SESSIONSDB_NO)
sessionsdb = sessionslib.SessionDBHandler(sessiondb_conn)


def gunicorn_setup_module():  # not working
    if os.path.exists(pid_path):
        os.remove(pid_path)
    cmd = f'gunicorn tests.service:__hug_wsgi__  -p {pid_path} -D'
    os.system(cmd)
    for i in range(10):
        if os.path.exists(pid_path):
            time.sleep(2)
            break


def gunicorn_teardown_module():
    if os.path.exists(pid_path):
        cmd = f'kill -9 `cat {pid_path}`'
        os.system(cmd)

def test_get():
    word = 'hello'
    url = echo_url + '/' + word
    assert requests.get(url, params=dict()).json() == word


def test_get_params():
    word = 'hello'
    url = echo_url + '/' + word
    params = {'word': word}
    assert requests.get(url, params=params).json() == word


def test_get_multi_params():
    nums = [3, 5, 8]
    url = base_url + 'add'
    params = {'nums': nums}
    assert requests.get(url, params=params).json() == 8#sum(nums)


def test_post():
    word = 'hello'
    url = echo_url
    assert requests.post(url, json={'word': word}).json()["word"] == word


def test_secure_echo():
    word = 'hello'
    headers = {'NoAuthorization': 'Header'}
    url = secure_echo_url + '/' + word
    resp = requests.get(url, headers=headers)
    assert resp.status_code == 401


def test_user_id():
    uid = 101
    d = dict(uid=uid, groups=[])
    sid = sessionsdb.create(**d)

    headers = {'Authorization': sid}

    word = 'hello'
    url = echo_url + '/' + word
    assert requests.get(url, headers=headers).json() == ('%s:%s' % (uid, word))

    url = base_url + 'me/uid'

    data = {'uid': None}
    resp = requests.post(url, json=data, headers=headers)
    assert resp.json() == uid

    data = {'uid': 1}  # invalid claim
    resp = requests.post(url, json=data, headers=headers)
    assert resp.json() == uid

    data = {'uid': uid}
    resp = requests.post(url, json=data, headers=headers)
    assert resp.json() == uid


def test_group_access():
    # 1. No group
    uid = 111
    groups = []
    d = dict(uid=uid, groups=groups)
    sid = sessionsdb.create(**d)
    url = echo_groups_url

    headers = {'Authorization': sid}
    assert requests.get(url, headers=headers).status_code == 403

    # 2. Forbidden group
    uid = 112
    groups = ['noaccess-group']
    d = dict(uid=uid, groups=groups)
    sid = sessionsdb.create(**d)
    url = echo_groups_url

    headers = {'Authorization': sid}
    assert requests.get(url, headers=headers).status_code == 403

    # 3. Access group
    uid = 113
    groups = ['access-group']
    d = dict(uid=uid, groups=groups)
    sid = sessionsdb.create(**d)

    headers = {'Authorization': sid}
    assert requests.get(url, headers=headers).status_code == 200
    assert requests.get(url, headers=headers).json() == groups

def test_not_found():
    url = base_url + 'snakes/viper'
    assert requests.get(url).status_code == 404

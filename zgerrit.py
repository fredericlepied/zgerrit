#!/usr/bin/env python
#
# Copyright (C) 2016 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

'''
'''

import getpass
import json
import os
import sys
import yaml

from txzmq import ZmqEndpoint
from txzmq import ZmqFactory
from txzmq import ZmqPubConnection
from twisted.internet import reactor
from twisted.python import log
from twisted.python.filepath import FilePath
from twisted.internet.protocol import ClientFactory, Protocol
from twisted.internet.endpoints import UNIXClientEndpoint
from twisted.conch.ssh.keys import EncryptedKeyError, Key
from twisted.conch.client.knownhosts import KnownHostsFile
from twisted.conch.endpoints import SSHCommandClientEndpoint

with open('config.yml') as f:
    _CONFIG = yaml.load(f.read())


def readKey(path):
    try:
        return Key.fromFile(path)
    except EncryptedKeyError:
        passphrase = getpass.getpass("%r keyphrase: " % (path,))
        return Key.fromFile(path, passphrase=passphrase)


class GerritJsonProtocol(Protocol):
    def __init__(self, zf):
        self.zmq_factory = zf

    def dataReceived(self, data):
        print 'received', data
        json_data = json.loads(data)
        if json_data and self.zmq_factory:
            for conn in self.zmq_factory.connections:
                conn.publish(json.dumps({'gerrit': json_data}))


class GerritJsonFactory(ClientFactory):
    protocol = GerritJsonProtocol

    def __init__(self, zf):
        self.zmq_factory = zf

    def buildProtocol(self, addr):
        return GerritJsonProtocol(self.zmq_factory)


class ConnectionParameters(object):
    def __init__(self, reactor, host, port, username, password, keys,
                 knownHosts, agent):
        self.reactor = reactor
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.keys = keys
        self.knownHosts = knownHosts
        self.agent = agent

    @classmethod
    def fromConfig(cls, reactor):
        keys = []
        if "identity" in _CONFIG:
            keyPath = os.path.expanduser(_CONFIG["identity"])
            if os.path.exists(keyPath):
                keys.append(readKey(keyPath))

        knownHostsPath = FilePath(os.path.expanduser(_CONFIG["knownhosts"]))
        if knownHostsPath.exists():
            knownHosts = KnownHostsFile.fromPath(knownHostsPath)
        else:
            knownHosts = None

        if "no-agent" in _CONFIG or "SSH_AUTH_SOCK" not in os.environ:
            agentEndpoint = None
        else:
            agentEndpoint = UNIXClientEndpoint(
                reactor, os.environ["SSH_AUTH_SOCK"])

        if "password" in _CONFIG:
            password = _CONFIG["password"]
        else:
            password = None

        return cls(
            reactor, _CONFIG["host"], _CONFIG["port"],
            _CONFIG["username"], password, keys,
            knownHosts, agentEndpoint)

    def endpointForStream(self):
        return SSHCommandClientEndpoint.newConnection(
            self.reactor, b"gerrit stream-events", self.username, self.host,
            port=self.port, keys=self.keys, password=self.password,
            agentEndpoint=self.agent, knownHosts=self.knownHosts)


if __name__ == '__main__':
    log.startLogging(sys.stderr)

    zf = ZmqFactory()
    e = ZmqEndpoint(_CONFIG['method'], _CONFIG['endpoint'])

    s = ZmqPubConnection(zf, e)

    parameters = ConnectionParameters.fromConfig(reactor)
    endpoint = parameters.endpointForStream()

    factory = GerritJsonFactory(zf)

    endpoint.connect(factory)

    reactor.run()

# zgerrit.py ends here

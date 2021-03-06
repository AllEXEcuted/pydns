#!/usr/bin/python3

import socket
from dns_message import DNSMessage, MessageType, RecordType
import os
import json
import time
import threading
import itertools


class CacheData(dict):
    def __init__(self, death_time=None, data=None):
        self._death_time = death_time
        self._data = data
        dict.__init__(self, death_time=death_time, data=data)

    @property
    def death_time(self):
        return self._death_time

    @death_time.setter
    def death_time(self, value):
        self._death_time = value
        self["death_time"] = value

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, value):
        self._data = value
        self["data"] = value

    def __eq__(self, other):
        return self.data == other.data

    def __hash__(self):
        return sum(map(hash, self.data))

    @staticmethod
    def loads(load):
        if not load:
            return {}
        for key in load:
            new_arr = []
            for rec in load[key]:
                new_arr.append(CacheData(rec["death_time"], rec["data"]))
            load[key] = new_arr
        return load

    @staticmethod
    def delete_old(data):
        for name, values in list(data.items()):
            data[name] = list(set(data[name]))
            i = 0
            while i < len(values):
                now_time = int(time.time())
                if values[i].death_time < now_time:
                    values.remove(values[i])
                else:
                    i += 1


class DNSServer:
    CACHE_FILES_NAMES = ["1", "2", "5", "6", "12", "13", "15", "28", "252", "255"]

    def __init__(self, host, port, asked_server):
        self._asked_server = asked_server
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.settimeout(1)
        self._sock.bind((host, port))
        self._requests = None
        self._list_answers = None
        self._is_listen = False
        self._cache_files = None

    @staticmethod
    def clear_cache():
        try:
            for file_name in DNSServer.CACHE_FILES_NAMES:
                with open("cache/%s.json" % file_name, "w") as file:
                    file.write("{}\n")
            print("Кэш сервера отчищен")
        except Exception as e:
            print("Кэш сервер НЕ отчищен %s" % e)

    def send_and_listen(self, data):
        try:
            self._is_listen = True
            address = self._asked_server, 53
            send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            send_sock.settimeout(1)
            send_sock.sendto(data, address)
            received_data, received_address = send_sock.recvfrom(2048)
            if received_address != address:
                return
            answer = DNSMessage().from_bytes(received_data)
            if answer:
                self._list_answers.add(answer)
        except Exception:
            pass
        finally:
            self._is_listen = False

    def _record_answers(self):
        rm_req = set()
        for request in self._requests:
            for answer in self._list_answers:
                for ans in itertools.chain(
                        answer.answers,
                        answer.auth_servers, answer.addit_records):
                    if ans.data:
                        cache_file = str(int(ans.request_type))
                        if not self._cache_files[cache_file].get(ans.name):
                            self._cache_files[cache_file][ans.name] = []
                        self._cache_files[cache_file][ans.name].append(
                            CacheData(ans.ttl + int(time.time()),
                                      list(ans.data)))
                        list(map(lambda i: CacheData.delete_old(i),
                                 self._cache_files.values()))
                if request[0].id == answer.id:
                    self._sock.sendto(
                        answer.to_bytes(), request[1])
                    rm_req.add(request)
                    break
        self._requests -= rm_req
        self._list_answers = set()

    def run(self):
        self._cache_files = dict(zip(
            DNSServer.CACHE_FILES_NAMES, [{}] * len(
                DNSServer.CACHE_FILES_NAMES)))
        for file_name in DNSServer.CACHE_FILES_NAMES:
            if os.path.exists("cache/%s.json" % file_name):
                with open("cache/%s.json" % file_name) as file:
                    try:
                        self._cache_files[file_name] = CacheData.loads(
                            json.load(file))
                    except json.JSONDecodeError:
                        pass
        try:
            list(map(lambda i: CacheData.delete_old(i),
                     self._cache_files.values()))
            self._requests = set()
            self._list_answers = set()
            while True:
                try:
                    data, address = self._sock.recvfrom(1024)
                    message = DNSMessage().from_bytes(bytearray(data))
                    list(map(lambda i: CacheData.delete_old(i),
                             self._cache_files.values()))
                    if not message:
                        continue
                    if message.response_type == MessageType.QUERY:
                        cache_file = self._cache_files[str(
                            int(message.questions[0].request_type))]
                        if cache_file.get(
                                message.questions[0].name):
                            send_data = DNSMessage.make_answer(message,
                                cache_file.get(
                                    message.questions[0].name)).to_bytes()
                            self._sock.sendto(send_data, address)
                            continue
                        self._requests.add((message, address))
                        threading.Thread(
                            target=self.send_and_listen, args=[data]).run()
                except socket.timeout:
                    pass
                finally:
                    if not self._is_listen:
                        self._record_answers()
        finally:
            for file_name in DNSServer.CACHE_FILES_NAMES:
                if os.path.exists("cache") and not os.path.isdir("cache"):
                    os.remove("cache")
                if not os.path.exists("cache"):
                    os.mkdir("cache")
                with open("cache/%s.json" % file_name, "w") as file:
                    json.dump(self._cache_files[file_name], file)
            self._sock.close()


if __name__ == '__main__':
    pass


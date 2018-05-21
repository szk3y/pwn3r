#!/usr/bin/env python3

from subprocess import Popen, PIPE
from time import sleep
import selectors
import signal
import socket
import subprocess
import sys

def _p8(num):
    return num.to_bytes(1, byteorder='little')

def _p16(num):
    return num.to_bytes(2, byteorder='little')

def _p32(num):
    return num.to_bytes(4, byteorder='little')

def _p64(num):
    return num.to_bytes(8, byteorder='little')

def u8(byte_string):
    if 1 < len(byte_string):
        print('Error: u8 gets too long string({})'.format(byte_string))
        sys.exit(1)
    return int.from_bytes(byte_string, byteorder='little')

def u16(byte_string):
    if 2 < len(byte_string):
        print('Error: u16 gets too long string({})'.format(byte_string))
        sys.exit(1)
    byte2 = byte_string.ljust(2, b'\0')
    return int.from_bytes(byte2, byteorder='little')

def u32(byte_string):
    if 4 < len(byte_string):
        print('Error: u32 gets too long string({})'.format(byte_string))
        sys.exit(1)
    byte4 = byte_string.ljust(4, b'\0')
    return int.from_bytes(byte4, byteorder='little')

def u64(byte_string):
    if 8 < len(byte_string):
        print('Error: u64 gets too long string({})'.format(byte_string))
        sys.exit(1)
    byte8 = byte_string.ljust(8, b'\0')
    return int.from_bytes(byte8, byteorder='little')

def p8(*nums):
    data = b''
    for num in nums:
        data += _p8(num)
    return data

def p16(*nums):
    data = b''
    for num in nums:
        data += _p16(num)
    return data

def p32(*nums):
    data = b''
    for num in nums:
        data += _p32(num)
    return data

def p64(*nums):
    data = b''
    for num in nums:
        data += _p64(num)
    return data

def xencode(string):
    if type(string) is str:
        return string.encode('ascii')
    else:
        return string

def xdecode(bytestr):
    if type(bytestr) is bytes:
        return bytestr.decode('ascii', 'backslashreplace')
    else:
        return bytestr

class Timeout(Exception):
    pass

def timeout_notice(sig, stack_frame):
    raise Timeout()

class Tube:
    def __init__(self, fin, fout, flog=sys.stdout, timeout=0, delay=0):
        self.is_silent = False
        self.fin = fin
        self.fout = fout
        self.flog = flog
        self.timeout = timeout
        self.delay = delay
        # It is not good to set a signal handler here
        signal.signal(signal.SIGALRM, timeout_notice)

    def shell(self):
        self.mute()
        selector = selectors.DefaultSelector()
        selector.register(self.fin, selectors.EVENT_READ)
        selector.register(sys.stdin, selectors.EVENT_READ)
        while True:
            signal.alarm(self.timeout)
            for key, events in selector.select():
                if key.fileobj is self.fin:
                    try:
                        data = self.recvline()
                    except EOFError:
                        print('End Of File')
                        return
                    sys.stdout.write(xdecode(data))
                    sys.stdout.flush()
                elif key.fileobj is sys.stdin:
                    line = input()
                    try:
                        self.fout.write(xencode(line) + b'\n')
                        self.fout.flush()
                    except BrokenPipeError:
                        print('Broken Pipe')
                        return

    def log(self, bytestr):
        if self.is_silent:
            return
        self.flog.write(xdecode(bytestr))
        self.flog.flush()

    def send(self, msg):
        sleep(self.delay)
        msg = xencode(msg)
        self.log(msg)
        self.fout.write(msg)
        self.fout.flush()

    def sendline(self, msg):
        self.send(xencode(msg) + b'\n')

    def sendint(self, num):
        self.sendline(str(num))

    def recv(self, num):
        signal.alarm(self.timeout)
        data = self.fin.read(num)
        signal.alarm(0)
        self.log(data)
        return data

    def recvuntil(self, delim):
        data = b''
        while not data.endswith(xencode(delim)):
            tmp = self.recv(1)
            data += tmp
        return data

    def recvline(self):
        return self.recvuntil(b'\n')

    def mute(self):
        self.is_silent = True

    def unmute(self):
        self.is_silent = False

class Process(Tube):
    def __init__(self, arglist, timeout=0, delay=0):
        p = Popen(arglist, stdin=PIPE, stdout=PIPE, stderr=subprocess.STDOUT)
        self.p = p
        super(Process, self).__init__(fin=p.stdout, fout=p.stdin, timeout=timeout, delay=delay)

    def close(self):
        self.p.terminate()

class Remote(Tube):
    def __init__(self, host, port, timeout=0, delay=0):
        ip = socket.gethostbyname(host)
        self.sock = socket.create_connection((ip, port))
        self.reader = self.sock.makefile(mode='rb', buffering=None)
        self.writer = self.sock.makefile(mode='wb', buffering=None)
        super(Remote, self).__init__(fin=self.reader, fout=self.writer, timeout=timeout, delay=delay)

    def close(self):
        self.reader.close()
        self.writer.close()
        self.sock.close()

if __name__ == '__main__':
    tube = Remote('localhost', 12345, timeout=3)
    #tube = Process(['cat'], timeout=3, delay=0.5)
    tube.sendline('Hello')
    print('Waiting...')
    try:
        tube.recvline()
        print('Successfully received!')
    except Timeout:
        print('Timeout!')
        sys.exit(0)
    try:
        tube.shell()
    except Timeout:
        print('Timeout!')
        tube.close()

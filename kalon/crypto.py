# dynDNS is a free tool aimed to help people managing their own DNS server(s) to
# update specific dynamic IP adresses automatically
# Copyright (C) 2015 toinews
#
# This file is part of dynDNS.
#
# dynDNS is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# dynDNS is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with dynDNS.  If not, see <http://www.gnu.org/licenses/>.

import base64
from Crypto.Cipher import AES
from Crypto import Random
from Crypto.Hash import SHA256
BS = 16


class AESCipher:
    key = None

    def __init__(self):
        pass

    @staticmethod
    def pad(s):
        return s + (BS - len(s) % BS) * chr(BS - len(s) % BS)

    @staticmethod
    def unpad(s):
        return s[:-ord(s[len(s)-1:])]

    @staticmethod
    def set_key(key):
        hash = SHA256.new()
        hash.update(key.encode('utf-8'))
        AESCipher.key = hash.digest()

    @staticmethod
    def encrypt(raw):
        raw = AESCipher.pad(raw)
        iv = Random.new().read(AES.block_size)
        cipher = AES.new(AESCipher.key, AES.MODE_CBC, iv)
        return base64.b64encode(iv + cipher.encrypt(raw))

    @staticmethod
    def decrypt(enc):
        enc = base64.b64decode(enc)
        iv = enc[:16]
        cipher = AES.new(AESCipher.key, AES.MODE_CBC, iv)
        return AESCipher.unpad(cipher.decrypt(enc[16:])).decode()
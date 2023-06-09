import json
import os

class Cache:
  VIN_SEEN = 'vin_seen'
  DEALER = 'dealer'

  def __init__(self, path):
    self._path = path

  def exists(self, typ, key):
    path = self._key_path(typ, key)
    return os.path.exists(path)

  def get(self, typ, key):
    path = self._key_path(typ, key)
    if os.path.exists(path):
      with open(path, 'r') as fd:
        return json.load(fd)
    return None

  def put(self, typ, key, value):
    path = self._key_path(typ, key)
    tmp_path = '%s.tmp' % (path,)
    with open(tmp_path, 'w') as fd:
      json.dump(value, fd)
    os.rename(tmp_path, path)
    return value

  def _key_path(self, typ, key):
    return os.path.join(self._path, '%s_%s.json' % (typ, key))

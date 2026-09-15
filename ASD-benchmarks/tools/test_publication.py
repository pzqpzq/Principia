#!/usr/bin/env python3
"""Check LFS pointer corruption behavior in an isolated temporary directory."""
import sys
sys.dont_write_bytecode = True
import hashlib,json,pathlib,tempfile
from verify_git_release import pointer_matches
from replay import check

with tempfile.TemporaryDirectory() as temporary:
    path=pathlib.Path(temporary)/'payload.bin'
    data=b'frozen scientific payload fixture\n'
    asset={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    pointer=(f"version https://git-lfs.github.com/spec/v1\noid sha256:{asset['sha256']}\nsize {asset['bytes']}\n").encode()
    assert not pointer_matches(path,asset)
    path.write_bytes(pointer)
    assert pointer_matches(path,asset)
    assert check(path,asset) != 'ok', 'pointer must never pass scientific payload verification'
    path.write_bytes(pointer.replace(asset['sha256'].encode(),b'0'*64))
    assert not pointer_matches(path,asset)
    path.write_bytes(pointer.replace(f"size {asset['bytes']}".encode(),b'size 1'))
    assert not pointer_matches(path,asset)
    path.write_bytes(pointer[:-1])
    assert not pointer_matches(path,asset)
    path.write_bytes(data)
    assert check(path,asset)=='ok'
    assert not pointer_matches(path,asset)
print(json.dumps({'status':'pass','checks':['missing pointer rejected','valid pointer metadata accepted','pointer rejected as scientific bytes','wrong object hash rejected','wrong object size rejected','truncated pointer rejected','real payload verified']}))

import numpy as np
import pytest
from amrs.face import choose_match,camera_source
from amrs.db import hash_password,check_password

def test_known_and_unknown_and_margin():
    matrix=np.array([[1,0,0],[0,1,0]],dtype=np.float32)
    assert choose_match(np.array([1,0,0],dtype=np.float32),matrix)[0]==0
    assert choose_match(np.array([0,0,1],dtype=np.float32),matrix)[0] is None
    assert choose_match(np.array([1,1,0],dtype=np.float32),matrix)[0] is None
    # Float32 dot products can exceed 1 by rounding; valid exact matches must
    # still produce a confidence accepted by the transactional repository.
    raw=np.random.default_rng(7).standard_normal((100,128)).astype('float32')
    for vector in raw:
        normalized=vector/(np.linalg.norm(vector)+1e-9)
        index,score=choose_match(vector,normalized.reshape(1,-1))
        assert index==0 and 0.0<=score<=1.0

def test_camera_source():
    assert camera_source('0')==0
    assert camera_source('rtsp://camera.local/live')=='rtsp://camera.local/live'
    with pytest.raises(ValueError):camera_source('bad-path')

def test_passwords():
    h=hash_password('some-good-password');assert check_password('some-good-password',h);assert not check_password('wrong',h)
    with pytest.raises(ValueError):hash_password('short')

def test_network_camera_opens_with_bounded_timeouts(monkeypatch):
    from amrs import face
    calls=[]
    sentinel=object()
    monkeypatch.setattr(face.cv2,'VideoCapture',lambda *args:(calls.append(args),sentinel)[1])
    assert face.open_camera('rtsp://camera.local/live') is sentinel
    assert calls[0][0]=='rtsp://camera.local/live' and calls[0][1]==face.cv2.CAP_FFMPEG
    assert face.cv2.CAP_PROP_OPEN_TIMEOUT_MSEC in calls[0][2]
    assert face.cv2.CAP_PROP_READ_TIMEOUT_MSEC in calls[0][2]

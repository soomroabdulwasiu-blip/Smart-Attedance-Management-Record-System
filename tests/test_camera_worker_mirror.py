import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from datetime import date
import numpy as np
from PySide6.QtCore import QEventLoop,QTimer
from PySide6.QtWidgets import QApplication
from amrs import db,face

def test_camera_mirror_keeps_recognition_raw_and_boxes_aligned(monkeypatch):
    app=QApplication.instance() or QApplication([])
    raw=np.zeros((100,120,3),dtype=np.uint8);raw[0,0]=[11,22,33];seen=[];frames=[];calls=[]
    student={'student_id':'S','roll_number':'KNOWN','face_enrolled':1}
    class FakeEngine:
        def load_references(self,students):return [(student,np.array([1.,0.],dtype=np.float32))],[]
        def detect(self,frame):return [np.array([10,35,20,20],dtype=np.float32)]
        def encode(self,frame,found):seen.append(frame[0,0].copy());return np.array([1.,0.],dtype=np.float32)
    class FakeCamera:
        def __init__(self,*args):pass
        def isOpened(self):return True
        def read(self):return True,raw.copy()
        def release(self):pass
    monkeypatch.setattr(face,'FaceEngine',FakeEngine);monkeypatch.setattr(face.cv2,'VideoCapture',FakeCamera)
    monkeypatch.setattr(db,'course_students',lambda course:[student]);monkeypatch.setattr(db,'authorized_course_students',lambda user,course:db.course_students(course));monkeypatch.setattr(db,'mark_attendance',lambda *a:calls.append(a))
    worker=face.CameraWorker({'role':'TEACHER','user_id':'T'},'C',date.today(),'0',mirror=True)
    worker.frame_ready.connect(lambda frame:frames.append(frame));worker.start()
    loop=QEventLoop();QTimer.singleShot(650,loop.quit);loop.exec();assert worker.stop()
    assert seen and all(np.array_equal(pixel,[11,22,33]) for pixel in seen)
    assert frames and np.array_equal(frames[-1][0,-1],[11,22,33])
    assert any(np.any(np.all(frame==[0,200,0],axis=2)) for frame in frames)
    assert len(calls)==1

import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from datetime import date
import numpy as np
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from amrs import db, face

def test_confirmation_only_after_database_success(monkeypatch):
    app=QApplication.instance() or QApplication([])
    student={'student_id':'S','roll_number':'R1','full_name':'Test Student','face_enrolled':1}
    class Engine:
        def load_references(self,students): return [(student,np.array([1.,0.],dtype=np.float32))],[]
        def detect(self,frame): return [np.array([10,10,20,20],dtype=np.float32)]
        def encode(self,frame,found): return np.array([1.,0.],dtype=np.float32)
    class Camera:
        def isOpened(self): return True
        def read(self): return True,np.zeros((80,80,3),dtype=np.uint8)
        def release(self): pass
    monkeypatch.setattr(face,'FaceEngine',Engine)
    monkeypatch.setattr(face,'open_camera',lambda source:Camera())
    monkeypatch.setattr(db,'course_students',lambda course:[student])
    monkeypatch.setattr(db,'authorized_course_students',lambda user,course:db.course_students(course))
    calls=[];events=[]
    monkeypatch.setattr(db,'mark_attendance',lambda *args:calls.append(args))
    worker=face.CameraWorker({'role':'TEACHER','user_id':'T'},'C',date.today(),'0')
    worker.attendance_saved.connect(lambda name,roll:events.append((name,roll)))
    worker.start();loop=QEventLoop();QTimer.singleShot(500,loop.quit);loop.exec();assert worker.stop()
    assert len(calls)==1 and events==[('Test Student','R1')]

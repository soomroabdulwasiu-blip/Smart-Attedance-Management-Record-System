import os,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
from datetime import date
from PySide6.QtCore import QEventLoop,QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from amrs import db,face
from amrs.gui import CameraPreview


def test_multiple_known_faces_and_unknown_save_only_confirmed_students(monkeypatch):
    app=QApplication.instance() or QApplication([])
    students=[{'student_id':'one','roll_number':'R1','full_name':'One','face_enrolled':1},
              {'student_id':'two','roll_number':'R2','full_name':'Two','face_enrolled':1}]
    class Engine:
        def load_references(self,items):return [(students[0],np.array([1.,0.,0.])),(students[1],np.array([0.,1.,0.]))],[]
        def detect(self,frame):return [np.array([15,20,35,45]),np.array([75,20,35,45]),np.array([135,20,35,45]),np.array([185,20,12,45])]
        def encode(self,frame,found):
            if int(found[0])==185:raise ValueError('Synthetic invalid crop')
            return {15:np.array([1.,0.,0.]),75:np.array([0.,1.,0.]),135:np.array([0.,0.,1.])}[int(found[0])]
    class Camera:
        def isOpened(self):return True
        def read(self):return True,np.zeros((100,200,3),dtype=np.uint8)
        def release(self):pass
    monkeypatch.setattr(face,'FaceEngine',Engine);monkeypatch.setattr(face,'open_camera',lambda _:Camera())
    monkeypatch.setattr(db,'course_students',lambda _:students)
    monkeypatch.setattr(db,'authorized_course_students',lambda user,course:db.course_students(course))
    calls=[];events=[];frames=[]
    def save(user,course,sid,*args):time.sleep(.08);calls.append(sid)
    monkeypatch.setattr(db,'mark_attendance',save)
    worker=face.CameraWorker({'role':'TEACHER','user_id':'T'},'C',date.today(),'0',mirror=True)
    worker.attendance_saved.connect(lambda name,roll:events.append(roll));worker.frame_ready.connect(frames.append);worker.start()
    loop=QEventLoop();QTimer.singleShot(1200,loop.quit);loop.exec();assert worker.stop()
    assert sorted(calls)==['one','two'] and sorted(events)==['R1','R2']
    assert any(np.any(np.all(frame==[0,200,0],axis=2)) and np.any(np.all(frame==[0,0,255],axis=2)) for frame in frames)


def test_resizable_preview_keeps_original_frame_and_aspect():
    app=QApplication.instance() or QApplication([])
    widget=CameraPreview();widget.resize(800,450)
    image=QImage(640,480,QImage.Format.Format_RGB32);image.fill(0xff145090)
    widget.setImage(image);widget.show();app.processEvents()
    assert widget.image.width()==640 and widget.image.height()==480
    shot=widget.grab().toImage()
    assert shot.pixelColor(0,shot.height()//2).name()=='#0a1220'
    assert shot.pixelColor(shot.width()//2,shot.height()//2).name()=='#145090'
    widget.resize(500,400);app.processEvents();assert widget.image.size()==image.size()
    widget.close()


def test_database_failure_does_not_show_success(monkeypatch):
    app=QApplication.instance() or QApplication([])
    student={'student_id':'one','roll_number':'R1','full_name':'One','face_enrolled':1}
    class Engine:
        def load_references(self,items):return [(student,np.array([1.,0.]))],[]
        def detect(self,frame):return [np.array([20,20,40,50])]
        def encode(self,frame,found):return np.array([1.,0.])
    class Camera:
        def isOpened(self):return True
        def read(self):return True,np.zeros((100,120,3),dtype=np.uint8)
        def release(self):pass
    def fail(*args):raise RuntimeError('Database unavailable')
    monkeypatch.setattr(face,'FaceEngine',Engine);monkeypatch.setattr(face,'open_camera',lambda _:Camera())
    monkeypatch.setattr(db,'course_students',lambda _:[student]);monkeypatch.setattr(db,'authorized_course_students',lambda user,course:db.course_students(course));monkeypatch.setattr(db,'mark_attendance',fail)
    events=[];messages=[];frames=[]
    worker=face.CameraWorker({'role':'TEACHER','user_id':'T'},'C',date.today(),'0')
    worker.attendance_saved.connect(lambda *a:events.append(a));worker.message.connect(messages.append);worker.frame_ready.connect(frames.append)
    worker.start();loop=QEventLoop();QTimer.singleShot(800,loop.quit);loop.exec();assert worker.stop()
    assert not events and any('Attendance failed' in m for m in messages)
    assert frames and not any(np.any(np.all(frame==[0,200,0],axis=2)) for frame in frames)

import os,contextlib,uuid,tempfile
from pathlib import Path
from datetime import date
import oracledb,cv2,numpy as np
from PySide6.QtCore import QCoreApplication,QTimer
from amrs import db,face
app=QCoreApplication([]);x=uuid.uuid4().hex[:8].upper();c=oracledb.connect(user='AMRS',password=os.environ['AMRS_DB_PASSWORD'],dsn='localhost:1521/FREEPDB1')
@contextlib.contextmanager
def shared():yield c
db.connection=shared;old_face=face.FACE_DIR;old_capture=face.cv2.VideoCapture;worker=None
try:
 with tempfile.TemporaryDirectory(dir='work') as tmp:
  face.FACE_DIR=Path(tmp);email='t'+x+'@example.test';db.signup_teacher('Temp Teacher',email,'Testing-123','Software Engineering');teacher=db.login('TEACHER',email,'Testing-123')
  db.add_course('T'+x,'Temp Course',3,1,teacher['user_id'],1);course=db.one('SELECT course_id FROM courses WHERE course_code=:code',{'code':'T'+x})['course_id']
  paths=list((Path.home()/'.amrs'/'faces').glob('*.png'))[:3];assert len(paths)==3
  eng=face.FaceEngine();crops=[];ids=[]
  for i,p in enumerate(paths):
   sid=db.add_student('Temp Student '+str(i),'T'+x+str(i),'','',1,1,2025);ids.append(sid);db.enroll_student(course,sid);eng.save_reference(sid,p)
   im=cv2.imdecode(np.fromfile(str(p),dtype=np.uint8),1);f=eng.detect(im)[0];xx,yy,ww,hh=map(int,f[:4]);xx=max(0,xx-ww//4);yy=max(0,yy-hh//4);crops.append(cv2.resize(im[yy:min(im.shape[0],yy+hh+hh//2),xx:min(im.shape[1],xx+ww+ww//2)],(300,350)))
  frame=np.hstack(crops)
  class Capture:
   def __init__(self,*a):pass
   def isOpened(self):return True
   def read(self):return True,frame.copy()
   def release(self):pass
  face.cv2.VideoCapture=Capture;events=[];worker=face.CameraWorker(teacher,course,date.today(),'0');worker.message.connect(events.append);worker.start();QTimer.singleShot(9000,app.quit);app.exec();assert worker.stop()
  records=db.attendance(teacher,course);assert len(records)==3 and {r['student_id'] for r in records}==set(ids),events
  assert all(r['status']=='PRESENT' and r['check_in_method']=='FACE' for r in records)
  print('PASS: three enrolled faces detected in one frame and saved as FACE attendance in Oracle')
finally:
 if worker and worker.isRunning():worker.stop()
 face.FACE_DIR=old_face;face.cv2.VideoCapture=old_capture;c.rollback();c.close();print('Temporary face test records rolled back')

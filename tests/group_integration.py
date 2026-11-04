from pathlib import Path
from datetime import date
import time, cv2,numpy as np
from PySide6.QtCore import QCoreApplication,QTimer
from amrs import db,face
paths=list((Path.home()/'.amrs'/'faces').glob('*.png'))[:3];assert len(paths)==3
eng=face.FaceEngine();crops=[];fake=[]
for i,p in enumerate(paths):
 im=cv2.imdecode(np.fromfile(str(p),dtype=np.uint8),1);f=eng.detect(im)[0];x,y,w,h=map(int,f[:4]);x=max(0,x-w//4);y=max(0,y-h//4);crop=im[y:min(im.shape[0],y+h+h//2),x:min(im.shape[1],x+w+w//2)];crops.append(cv2.resize(crop,(300,350)));fake.append({'student_id':p.stem,'roll_number':'TEST-'+str(i),'full_name':'Test','face_enrolled':1})
frame=np.hstack(crops);calls=[]
class Capture:
 def __init__(self,*a):pass
 def isOpened(self):return True
 def read(self):return True,frame.copy()
 def release(self):pass
face.cv2.VideoCapture=Capture;db.course_students=lambda _:fake;db.mark_attendance=lambda user,course,sid,day,status,method,score:calls.append(sid)
app=QCoreApplication([]);worker=face.CameraWorker({'role':'TEACHER','user_id':'T'},'C',date.today(),'0');events=[];worker.message.connect(events.append);worker.start();QTimer.singleShot(8000,app.quit);app.exec();worker.stop()
print('Synthetic group attendance calls:',len(calls),'unique:',len(set(calls)));print('Statuses:',events)
assert len(calls)==3 and len(set(calls))==3

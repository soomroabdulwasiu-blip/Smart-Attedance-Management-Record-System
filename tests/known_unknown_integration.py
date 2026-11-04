from pathlib import Path
from datetime import date
import cv2,numpy as np
from PySide6.QtCore import QCoreApplication,QTimer
from amrs import db,face
paths=list((Path.home()/'.amrs'/'faces').glob('*.png'));assert len(paths)>=2
eng=face.FaceEngine();vectors=[]
for p in paths:
 try:
  f=eng.reference(p);vectors.append((p,f/(np.linalg.norm(f)+1e-9)))
 except ValueError:pass
pair=min(((float(a[1]@b[1]),a[0],b[0]) for i,a in enumerate(vectors) for b in vectors[i+1:]),key=lambda x:x[0]);assert pair[0]<.5,pair[0]
crops=[]
for p in pair[1:]:
 im=cv2.imdecode(np.fromfile(str(p),dtype=np.uint8),1);f=eng.detect(im)[0];x,y,w,h=map(int,f[:4]);x=max(0,x-w//4);y=max(0,y-h//4);crop=im[y:min(im.shape[0],y+h+h//2),x:min(im.shape[1],x+w+w//2)];crops.append(cv2.resize(crop,(300,350)))
frame=np.hstack(crops);student={'student_id':pair[1].stem,'roll_number':'TEST-KNOWN','full_name':'Test','face_enrolled':1};calls=[];last=[]
class Capture:
 def __init__(self,*a):pass
 def isOpened(self):return True
 def read(self):return True,frame.copy()
 def release(self):pass
face.cv2.VideoCapture=Capture;db.course_students=lambda _: [student];db.mark_attendance=lambda user,course,sid,day,status,method,score:calls.append(sid)
app=QCoreApplication([]);w=face.CameraWorker({'role':'TEACHER','user_id':'T'},'C',date.today(),'0');w.frame_ready.connect(lambda f:last.__setitem__(slice(None),[f]));w.start();QTimer.singleShot(7000,app.quit);app.exec();w.stop()
assert calls==[student['student_id']],calls
assert last and np.any(np.all(last[0]==[0,200,0],axis=2)) and np.any(np.all(last[0]==[0,0,255],axis=2))
print('PASS: known face marked once and green; distinct unenrolled face red and unmarked')

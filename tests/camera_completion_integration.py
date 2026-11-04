from pathlib import Path
from datetime import date
import time,cv2,numpy as np
from PySide6.QtCore import QCoreApplication,QTimer
from amrs import db,face
p=next((Path.home()/'.amrs'/'faces').glob('*.png'));frame=cv2.imdecode(np.fromfile(str(p),dtype=np.uint8),1);empty=np.zeros_like(frame);student={'student_id':p.stem,'roll_number':'TEMP','full_name':'Test','face_enrolled':1}
class Capture:
 def __init__(self,*a):self.n=0
 def isOpened(self):return True
 def read(self):self.n+=1;return True,(frame.copy() if self.n<=3 else empty.copy())
 def release(self):pass
face.cv2.VideoCapture=Capture;db.course_students=lambda _: [student]
def save(*args):time.sleep(.2)
db.mark_attendance=save
app=QCoreApplication([]);worker=face.CameraWorker({'role':'TEACHER','user_id':'T'},'C',date.today(),'0');events=[];worker.message.connect(events.append);worker.start();QTimer.singleShot(6500,app.quit);app.exec();worker.stop()
assert any('attendance saved' in e for e in events),events
print('PASS: completed attendance is reported after face leaves the frame')

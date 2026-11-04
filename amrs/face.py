"""YuNet + SFace multi-person recognition. Thresholds require local evaluation."""
from pathlib import Path
from datetime import date
from concurrent.futures import ThreadPoolExecutor
import os,time,json,re,threading,cv2,numpy as np
from PySide6.QtCore import QThread,Signal
from . import db
from . import privacy
from .mail_delivery import _crypt
from .paths import DATA_ROOT
ROOT=Path(__file__).resolve().parent.parent
FACE_DIR=DATA_ROOT/'faces'
LEGACY_FACE_DIR=Path.home()/'.amrs'/'faces'
DETECTOR=ROOT/'models'/'face_detection_yunet_2023mar.onnx'
RECOGNIZER=ROOT/'models'/'face_recognition_sface_2021dec.onnx'
THRESHOLD=.55
MARGIN=.08

def safe_student_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',value):raise ValueError('Invalid student reference.')
    return value

class FaceEngine:
    def __init__(self):
        from .config import load
        global THRESHOLD,MARGIN
        config=load();THRESHOLD=config.face_threshold;MARGIN=config.face_margin
        if not DETECTOR.is_file() or not RECOGNIZER.is_file():raise RuntimeError('Face model files are missing.')
        self.detector=cv2.FaceDetectorYN.create(str(DETECTOR),'',(320,320),0.85,0.3,5000)
        self.recognizer=cv2.FaceRecognizerSF.create(str(RECOGNIZER),'')
    def detect(self,frame):
        h,w=frame.shape[:2];self.detector.setInputSize((w,h));_,faces=self.detector.detect(frame)
        return list(faces) if faces is not None else []
    def encode(self,frame,face):
        crop=self.recognizer.alignCrop(frame,face);return self.recognizer.feature(crop).reshape(-1).astype('float32')
    def reference(self,path):
        image=cv2.imdecode(np.fromfile(str(path),dtype=np.uint8),cv2.IMREAD_COLOR)
        if image is None:raise ValueError('Cannot read image.')
        faces=self.detect(image)
        if len(faces)!=1:raise ValueError(f'Expected one clear face in photo; detected {len(faces)}.')
        return self.encode(image,faces[0])
    def save_reference(self,student_id,path):
        self.save_reference_bytes(student_id,Path(path).read_bytes())
    def save_reference_bytes(self,student_id,raw):
        safe_student_id(student_id)
        if not privacy.has_consent(student_id):raise ValueError('Explicit biometric consent is required before enrollment.')
        image=cv2.imdecode(np.frombuffer(raw,dtype=np.uint8),cv2.IMREAD_COLOR)
        if image is None:raise ValueError('Cannot read the selected image.')
        faces=self.detect(image)
        if len(faces)!=1:raise ValueError(f'One clear face is required; detected {len(faces)}.')
        feature=self.encode(image,faces[0])
        if feature.shape!=(128,) or not np.isfinite(feature).all() or np.linalg.norm(feature)<1e-9:raise ValueError('The face representation is invalid.')
        payload=_crypt(json.dumps({'student_id':student_id,'model':RECOGNIZER.name,'feature':(feature/np.linalg.norm(feature)).tolist()}).encode())
        FACE_DIR.mkdir(parents=True,exist_ok=True)
        dest=FACE_DIR/(student_id+'.template');tmp=FACE_DIR/(student_id+'.tmp');previous=dest.read_bytes() if dest.exists() else None;tmp.write_bytes(payload)
        try:
            tmp.replace(dest);db.set_face_enrolled(student_id)
        except Exception:
            tmp.unlink(missing_ok=True)
            if previous is None:dest.unlink(missing_ok=True)
            else:dest.write_bytes(previous)
            raise
    def load_references(self,students):
        refs=[];skipped=[]
        for s in students:
            if not s['face_enrolled']:continue
            safe_student_id(s['student_id'])
            if not privacy.has_consent(s['student_id']):
                skipped.append(s['roll_number']+': consent required');continue
            template=FACE_DIR/(s['student_id']+'.template')
            if template.exists():
                try:
                    data=json.loads(_crypt(template.read_bytes(),True).decode())
                    if data['student_id']!=s['student_id'] or data['model']!=RECOGNIZER.name:raise ValueError('Template identity/version mismatch.')
                    f=np.asarray(data['feature'],dtype='float32')
                    if f.shape!=(128,) or not np.isfinite(f).all() or np.linalg.norm(f)<1e-9:raise ValueError('Invalid template.')
                    refs.append((s,f/(np.linalg.norm(f)+1e-9)))
                except Exception:skipped.append(s['roll_number']+': encrypted template unavailable; re-enrollment required')
                continue
            p=FACE_DIR/(s['student_id']+'.image')
            if not p.exists():p=LEGACY_FACE_DIR/(s['student_id']+'.png')
            if not p.exists():
                if s['face_enrolled']:skipped.append(s['roll_number']+': missing photo')
                continue
            try:
                f=self.reference(p);refs.append((s,f/(np.linalg.norm(f)+1e-9)))
            except Exception as e:skipped.append(s['roll_number']+': '+str(e))
        return refs,skipped

def choose_match(feature,matrix):
    if not np.isfinite(feature).all() or not np.isfinite(matrix).all() or np.linalg.norm(feature)<1e-9:return None,0.0
    feature=feature/(np.linalg.norm(feature)+1e-9);scores=np.clip(matrix@feature,-1.0,1.0);order=np.argsort(scores)[::-1]
    if not len(order):return None,0.0
    index=int(order[0]);best=float(scores[index]);second=float(scores[order[1]]) if len(order)>1 else -1.0
    return (index if best>=THRESHOLD and best-second>=MARGIN else None),best

def preview_frame(frame,mirror=False):
    """Orient a display copy only; recognition and saved images remain unchanged."""
    return cv2.flip(frame,1) if mirror else frame.copy()

def preview_box(x,y,w,h,frame_width,mirror=False):
    return (frame_width-x-w if mirror else x,y,w,h)

def draw_face_status(frame, box, label, color):
    """Draw readable, clipped labels without changing the recognition frame."""
    height,width=frame.shape[:2]
    x,y,w,h=map(int,box)
    x=max(0,min(width-1,x));y=max(0,min(height-1,y))
    x2=max(x,min(width-1,x+max(1,w)));y2=max(y,min(height-1,y+max(1,h)))
    thickness=max(2,round(width/500))
    cv2.rectangle(frame,(x,y),(x2,y2),color,thickness)
    scale=max(.42,min(.75,width/1000))
    font=cv2.FONT_HERSHEY_SIMPLEX
    (tw,th),baseline=cv2.getTextSize(label,font,scale,1)
    # Place labels inside the image, below a face when its top is too close to the edge.
    lx=max(0,min(x,width-tw-12));ly=y-th-baseline-12
    if ly<0:ly=min(height-th-baseline-10,y2+3)
    ly=max(0,ly);right=min(width-1,lx+tw+12);bottom=min(height-1,ly+th+baseline+10)
    cv2.rectangle(frame,(lx,ly),(right,bottom),color,-1)
    cv2.putText(frame,label,(lx+6,min(height-2,ly+th+4)),font,scale,(0,0,0),1,cv2.LINE_AA)

def camera_source(value):
    value=str(value).strip()
    if value.isdecimal():return int(value)
    if value.startswith(('rtsp://','http://','https://')):return value
    raise ValueError('Use a camera number such as 0 or a valid RTSP/HTTP camera URL.')

def open_camera(source):
    source=camera_source(source)
    if isinstance(source,int):
        return cv2.VideoCapture(source,cv2.CAP_DSHOW if os.name=='nt' else cv2.CAP_ANY)
    # Network cameras need a bounded open/read time so Stop can recover from disconnection.
    params=[cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,5000,cv2.CAP_PROP_READ_TIMEOUT_MSEC,3000]
    return cv2.VideoCapture(source,cv2.CAP_FFMPEG,params)

def _capture(source,user=None):
    if str(source).startswith('device:'):
        from .devices import adapter_for
        cap=adapter_for(user,str(source)[7:]);cap.connect();return cap
    return open_camera(source)

def _read(cap,worker):
    from .cameras import valid_frame
    ok,frame=cap.read()
    if ok and valid_frame(frame):return True,frame
    if hasattr(cap,'reconnect') and worker.running:
        worker.message.emit('Camera interrupted. Reconnecting within the configured retry limit…')
        if cap.reconnect(worker.cancel_event) and worker.running:
            ok,frame=cap.read()
            if ok and valid_frame(frame):return True,frame
    return False,None

class BatchEnrollmentWorker(QThread):
    progress=Signal(int,str)
    completed=Signal(int,int,bool)
    def __init__(self,entries,parent=None):
        super().__init__(parent);self.entries=list(entries);self.cancelled=False
    def cancel(self):self.cancelled=True
    def run(self):
        success=0;processed=0
        try:
            engine=FaceEngine()
            for i,(sid,name,path) in enumerate(self.entries):
                if self.cancelled:break
                try:engine.save_reference(sid,path);status='Enrolled';success+=1
                except Exception as exc:status='Failed: '+str(exc)
                processed+=1;self.progress.emit(i,status)
        except Exception as exc:
            for i in range(processed,len(self.entries)):
                self.progress.emit(i,'Failed: '+str(exc))
        finally:self.completed.emit(success,processed,self.cancelled)

class CaptureEnrollmentWorker(QThread):
    frame_ready=Signal(object,object,int)
    message=Signal(str)
    def __init__(self,source,parent=None,user=None):
        super().__init__(parent);self.source=source;self.user=user;self.running=True;self.cancel_event=threading.Event()
    def stop(self):
        self.running=False;self.cancel_event.set();return self.wait(9000)
    def run(self):
        cap=None
        try:
            engine=FaceEngine();cap=_capture(self.source,self.user)
            if not cap.isOpened():raise RuntimeError('Camera could not be opened. Check its source or close other apps using it.')
            self.message.emit('Camera ready. Position one face in the frame.')
            while self.running:
                ok,frame=_read(cap,self)
                if not ok:raise RuntimeError('Camera stopped returning frames.')
                faces=engine.detect(frame);preview=frame.copy()
                for found in faces:
                    x,y,w,h=map(int,found[:4]);cv2.rectangle(preview,(x,y),(x+w,y+h),(0,185,0) if len(faces)==1 else (0,0,255),2)
                self.frame_ready.emit(frame.copy(),preview,len(faces));self.msleep(60)
        except Exception as exc:self.message.emit('Camera error: '+str(exc))
        finally:
            if cap is not None:cap.release()

class CameraProbeWorker(QThread):
    frame_ready=Signal(object)
    message=Signal(str)
    def __init__(self,source,parent=None,mirror=False,user=None):
        super().__init__(parent);self.source=source;self.user=user;self.running=True;self.mirror=mirror;self.cancel_event=threading.Event()
    def stop(self):
        self.running=False;self.cancel_event.set();return self.wait(7000)
    def run(self):
        cap=None
        try:
            cap=_capture(self.source,self.user)
            if not cap.isOpened():raise RuntimeError('Camera could not be opened. Check the source and device connection.')
            self.message.emit('Camera connected. This is a preview; attendance is not being marked.')
            while self.running:
                ok,frame=_read(cap,self)
                if not ok:raise RuntimeError('Camera stopped returning frames.')
                self.frame_ready.emit(preview_frame(frame,self.mirror));self.msleep(35)
        except Exception as e:self.message.emit('Camera error: '+str(e))
        finally:
            if cap is not None:cap.release()

class CameraWorker(QThread):
    frame_ready=Signal(object)
    message=Signal(str)
    attendance_saved=Signal(str,str)
    def __init__(self,user,course,day,source,parent=None,mirror=False):
        super().__init__(parent);self.user=user;self.course=course;self.day=day;self.source=source;self.running=True;self.mirror=mirror;self.cancel_event=threading.Event()
    def stop(self):
        self.running=False
        self.cancel_event.set()
        return self.wait(6000)
    def run(self):
        cap=None;executor=ThreadPoolExecutor(max_workers=2)
        try:
            engine=FaceEngine();refs,skipped=engine.load_references(db.authorized_course_students(self.user,self.course))
            if skipped:self.message.emit('Some references could not load: '+', '.join(skipped))
            if not refs:raise ValueError('No usable enrolled faces in this course. Enroll clear photos first.')
            matrix=np.stack([v for _,v in refs]);cap=_capture(self.source,self.user)
            if not cap.isOpened():raise RuntimeError('Could not open the selected camera.')
            counts={};marked=set();pending={};retry_after={};self.message.emit(f'Camera started. {len(refs)} reference faces loaded.')
            def collect_completed():
                for sid,(future,student) in list(pending.items()):
                    roll=student['roll_number']
                    if not future.done():continue
                    try:
                        future.result();marked.add(sid);self.message.emit(roll+' attendance saved');self.attendance_saved.emit(student.get('full_name') or roll,roll)
                    except Exception as e:
                        retry_after[sid]=time.monotonic()+5;self.message.emit('Attendance failed for '+roll+': '+str(e))
                    del pending[sid]
            while self.running:
                collect_completed()
                ok,frame=_read(cap,self)
                if not ok:raise RuntimeError('Camera stopped returning frames.')
                faces=engine.detect(frame);mirror=bool(self.mirror);display=preview_frame(frame,mirror);seen=set();detections=[]
                for face in faces:
                    try:
                        feature=engine.encode(frame,face);idx,best=choose_match(feature,matrix)
                        student=refs[idx][0] if idx is not None else None
                    except (ValueError,TypeError,cv2.error):
                        # One poor/edge-of-frame face must not stop other students.
                        student=None;best=0.0
                    detections.append((face,student,best))
                # Two visible faces must never both be accepted as the same identity.
                all_ids=[s['student_id'] for _,s,_ in detections if s]
                for face,s,score in detections:
                    if s and all_ids.count(s['student_id'])>1:s=None
                    x,y,w,h=map(int,face[:4]);x,y,w,h=preview_box(x,y,w,h,frame.shape[1],mirror);label='Unknown';color=(0,0,255)
                    if s:
                        sid=s['student_id'];seen.add(sid);counts[sid]=counts.get(sid,0)+1
                        if counts[sid]>=3 and sid not in marked and sid not in pending and time.monotonic()>=retry_after.get(sid,0):
                            pending[sid]=(executor.submit(db.mark_attendance,self.user,self.course,sid,self.day,'PRESENT','FACE',score),s)
                        if sid in marked:label=s['roll_number']+' PRESENT';color=(0,200,0)
                        elif sid in pending:label=s['roll_number']+' SAVING';color=(0,180,255)
                        elif time.monotonic()<retry_after.get(sid,0):label=s['roll_number']+' RETRYING';color=(0,180,255)
                        else:label=s['roll_number']+' VERIFYING';color=(0,180,255)
                    draw_face_status(display,(x,y,w,h),label,color)
                counts={k:v for k,v in counts.items() if k in seen};self.frame_ready.emit(display);self.msleep(40)
        except Exception as e:self.message.emit('Camera error: '+str(e))
        finally:
            if cap is not None:cap.release()
            executor.shutdown(wait=True)
            if 'pending' in locals():collect_completed()
            self.message.emit('Camera stopped.')

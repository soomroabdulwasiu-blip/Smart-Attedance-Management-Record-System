import os,uuid,contextlib,tempfile
from pathlib import Path
import oracledb
from PySide6.QtWidgets import QApplication,QDialog,QMessageBox
from amrs import db,gui,face
app=QApplication([]);app.setStyleSheet(gui.STYLE);errors=[];gui.error=lambda p,e:errors.append(str(e));gui.alert=lambda *a:None
c=oracledb.connect(user='AMRS',password=os.environ['AMRS_DB_PASSWORD'],dsn='localhost:1521/FREEPDB1')
@contextlib.contextmanager
def shared():yield c
db.connection=shared
x=uuid.uuid4().hex[:8].upper();saved_face_dir=face.FACE_DIR
class FakeCapture:
 def __init__(self,*args):self.capture_bytes=next((Path.home()/'.amrs'/'faces').glob('*.png')).read_bytes()
 def exec(self):return QDialog.DialogCode.Accepted
gui.CameraCaptureDialog=FakeCapture
try:
 with tempfile.TemporaryDirectory(dir='work') as tmp:
  face.FACE_DIR=Path(tmp)
  u=db.one("SELECT u.user_id,u.full_name,u.email FROM users u JOIN roles r ON r.role_id=u.role_id WHERE r.role_name='ADMIN' AND u.is_active=1 FETCH FIRST 1 ROWS ONLY");u['role']='ADMIN'
  login=gui.Login();w=gui.MainWindow(u,login);w.show();app.processEvents()
  w.s_name.setText('Temporary Test Student');w.s_roll.setText('T'+x);w.s_email.setText('s'+x+'@example.test');w.add_student();app.processEvents();assert not errors,errors
  sid=w.selected_student_id;assert sid and db.one('SELECT student_id FROM students WHERE student_id=:id',{'id':sid})
  w.s_name.setText('Temporary Updated Student');w.save_student();assert not errors,errors
  w.s_login_email.setText('s'+x+'@example.test');w.s_login_password.setText('Testing-123');w.create_login();assert not errors,errors
  assert db.login('STUDENT','T'+x,'Testing-123')['user_id']==sid
  w.enroll_face_camera();assert not errors,errors;assert db.one('SELECT face_enrolled FROM students WHERE student_id=:id',{'id':sid})['face_enrolled']==1
  assert (face.FACE_DIR/(sid+'.image')).exists()
  w.clear_student_form();w.s_name.setText('Second Temporary Student');w.s_roll.setText('U'+x);w.s_email.setText('u'+x+'@example.test');w.add_student_and_capture();assert not errors,errors
  second=w.selected_student_id;assert second and db.one('SELECT face_enrolled FROM students WHERE student_id=:id',{'id':second})['face_enrolled']==1
  w.t_name.setText('Temporary Test Teacher');w.t_email.setText('t'+x+'@example.test');w.t_password.setText('Testing-123');w.register_teacher();assert not errors,errors
  teacher=db.one('SELECT user_id FROM users WHERE LOWER(email)=LOWER(:email)',{'email':'t'+x+'@example.test'})['user_id'];w.teacher.setCurrentIndex(w.teacher.findData(teacher))
  w.course_code.setText('T'+x);w.course_name.setText('Temporary Test Course');w.create_course();assert not errors,errors
  cid=db.one('SELECT course_id FROM courses WHERE course_code=:code',{'code':'T'+x})['course_id'];w.admin_course.setCurrentIndex(w.admin_course.findData(cid));w.admin_student.setCurrentIndex(w.admin_student.findData(sid));w.enroll();assert not errors,errors
  assert sid in [r['student_id'] for r in db.course_students(cid)]
  print('PASS: inline admin add/edit student, login, camera capture save, teacher registration, course creation and enrollment');w.close()
finally:
 face.FACE_DIR=saved_face_dir;c.rollback();c.close();print('Temporary records rolled back')

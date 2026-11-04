import os,contextlib,uuid,tempfile
from datetime import date
from pathlib import Path
import oracledb
from amrs import db,face
x=uuid.uuid4().hex[:8].upper();c=oracledb.connect(user='AMRS',password=os.environ['AMRS_DB_PASSWORD'],dsn='localhost:1521/FREEPDB1')
@contextlib.contextmanager
def shared():yield c
db.connection=shared
try:
 teacher_email='T'+x+'@example.test';db.signup_teacher('Test Teacher',teacher_email,'Testing-123','Software Engineering');teacher=db.login('TEACHER',teacher_email,'Testing-123')
 sid=db.add_student('Test Student','T'+x,'student@example.test','',1,1,2025);assert sid
 db.update_student(sid,'Test Updated','student@example.test','',1,2,2025)
 db.create_student_login(sid,'test'+x+'@example.test','Testing-123');assert db.login('STUDENT','T'+x,'Testing-123')['user_id']==sid
 db.add_course('T'+x,'Test Course',3,1,teacher['user_id'],2);course=db.one('SELECT course_id FROM courses WHERE course_code=:code',{'code':'T'+x})['course_id']
 count=db.enroll_all_students(course);assert count>=1 and db.enroll_all_students(course)==0;assert sid in [r['student_id'] for r in db.course_students(course)]
 with tempfile.TemporaryDirectory(dir='work') as tmp:
  face.FACE_DIR=Path(tmp);photo=next((Path.home()/'.amrs'/'faces').glob('*.png'));face.FaceEngine().save_reference(sid,photo)
  assert db.one('SELECT face_enrolled FROM students WHERE student_id=:id',{'id':sid})['face_enrolled']==1
  assert (face.FACE_DIR/(sid+'.image')).exists()
 db.mark_attendance(teacher,course,sid,date.today(),'PRESENT','MANUAL')
 db.request_reset('STUDENT','test'+x+'@example.test','Test Updated','New-pass-123')
 db.delete_student_permanently(sid)
 assert db.one('SELECT attendance_id FROM attendance WHERE student_id=:id',{'id':sid}) is None
 assert db.one("SELECT request_id FROM password_reset_requests WHERE user_type='STUDENT' AND user_id=:id",{'id':sid}) is None
 assert db.one('SELECT student_id FROM students WHERE student_id=:id',{'id':sid}) is None
 assert db.one('SELECT login_id FROM student_logins WHERE student_id=:id',{'id':sid}) is None
 assert db.one('SELECT enrollment_id FROM course_enrollments WHERE student_id=:id AND course_id=:course',{'id':sid,'course':course}) is None
 print('PASS: student CRUD, student login, teacher registration, course, enroll all, face storage and delete cascades')
finally:
 c.rollback();c.close();print('Temporary database changes rolled back')

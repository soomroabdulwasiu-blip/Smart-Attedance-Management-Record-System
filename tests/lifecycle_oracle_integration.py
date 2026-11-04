import os,contextlib,uuid
from datetime import date
import oracledb
from PySide6.QtWidgets import QApplication,QMessageBox
from amrs import db,gui

app=QApplication([]);errors=[];gui.error=lambda _,e:errors.append(str(e));gui.alert=lambda *args:None
QMessageBox.question=lambda *args:QMessageBox.StandardButton.Yes
c=oracledb.connect(user='AMRS',password=os.environ['AMRS_DB_PASSWORD'],dsn='localhost:1521/FREEPDB1')
@contextlib.contextmanager
def shared():yield c
db.connection=shared;x=uuid.uuid4().hex[:8].upper()
try:
 admin=db.one("SELECT u.user_id,u.full_name,u.email FROM users u JOIN roles r ON r.role_id=u.role_id WHERE r.role_name='ADMIN' AND u.is_active=1 FETCH FIRST 1 ROWS ONLY");admin['role']='ADMIN'
 email='t'+x.lower()+'@example.test';roll='S'+x;student_email='s'+x.lower()+'@example.test';code='C'+x
 db.signup_teacher('Teacher',email,'Testing-123','Department');teacher=db.login('TEACHER',email,'Testing-123')
 db.signup_student('Student',student_email,'Testing-123',roll,1,1,2025);student=db.login('STUDENT',roll,'Testing-123')
 db.add_course(code,'Course',3,1,teacher['user_id'],1);cid=db.course_for_code(code)['course_id'];db.enroll_student(cid,student['user_id']);db.mark_attendance(teacher,cid,student['user_id'],date.today(),'PRESENT','MANUAL')
 for attempt in (lambda:db.signup_student('Duplicate',student_email,'Testing-123',roll,1,1,2025), lambda:db.signup_student('Duplicate',student_email,'Testing-123','Z'+x,1,1,2025), lambda:db.add_student('Duplicate','Z'+x,student_email,'',1,1,2025), lambda:db.request_teacher_signup('Duplicate',email,'Testing-123','Department')):
  try:attempt()
  except ValueError:pass
  else:raise AssertionError('Active duplicate was accepted')
 db.delete_student_permanently(student['user_id']);db.signup_student('New Student',student_email,'Testing-123',roll,1,1,2025)
 new=db.login('STUDENT',roll,'Testing-123');assert new['user_id']!=student['user_id'] and not db.attendance(new,cid)
 db.enroll_student(cid,new['user_id']);db.mark_attendance(teacher,cid,new['user_id'],date.today(),'PRESENT','MANUAL')
 db.delete_course_permanently(cid);assert not db.course_for_code(code)
 db.add_course(code,'New Course',3,1,teacher['user_id'],1);cid2=db.course_for_code(code)['course_id'];db.enroll_student(cid2,new['user_id']);db.mark_attendance(teacher,cid2,new['user_id'],date.today(),'PRESENT','MANUAL')
 db.delete_teacher_permanently(teacher['user_id']);assert not db.teacher_for_email(email) and not db.course_for_code(code)
 db.request_teacher_signup('New Teacher',email,'Testing-123','Department')
 request=next(r for r in db.pending_teacher_signups(admin) if r['email']==email);db.resolve_teacher_signup(admin,request['request_id'],True)
 teacher2=db.login('TEACHER',email,'Testing-123');assert teacher2['user_id']!=teacher['user_id']
 db.add_course(code,'Third Course',3,1,teacher2['user_id'],1)
 assert not errors,errors
 print('PASS: active duplicates rejected; permanent student/course/teacher deletion releases identifiers and removes linked records')
finally:c.rollback();c.close();print('Temporary records rolled back')

import os,contextlib,uuid
from datetime import date
import oracledb
from PySide6.QtWidgets import QApplication
from amrs import db,gui

app=QApplication([]);errors=[];gui.error=lambda _,e:errors.append(str(e));gui.alert=lambda *args:None
c=oracledb.connect(user='AMRS',password=os.environ['AMRS_DB_PASSWORD'],dsn='localhost:1521/FREEPDB1')
@contextlib.contextmanager
def shared():yield c
db.connection=shared;x=uuid.uuid4().hex[:8].upper()
try:
 adminrow=db.one("SELECT u.user_id,u.full_name,u.email FROM users u JOIN roles r ON r.role_id=u.role_id WHERE r.role_name='ADMIN' AND u.is_active=1 FETCH FIRST 1 ROWS ONLY")
 admin=dict(adminrow,role='ADMIN');teacher_email='q'+x+'@example.test'
 db.request_teacher_signup('Pending Teacher',teacher_email,'Testing-123','Software Engineering')
 try:db.login('TEACHER',teacher_email,'Testing-123')
 except ValueError:pass
 else:raise AssertionError('Pending teacher was allowed to log in')
 request=next(r for r in db.pending_teacher_signups(admin) if r['email']==teacher_email.lower())
 db.resolve_teacher_signup(admin,request['request_id'],True)
 teacher=db.login('TEACHER',teacher_email,'Testing-123')
 email='s'+x+'@example.test';roll='R'+x
 db.signup_student('Temporary Student',email,'Testing-123',roll,1,1,2025);student=db.login('STUDENT',roll,'Testing-123')
 db.add_course('C'+x,'Temp Course',3,1,teacher['user_id'],1);course=db.one('SELECT course_id FROM courses WHERE course_code=:code',{'code':'C'+x})['course_id'];db.enroll_student(course,student['user_id'])
 db.mark_attendance(teacher,course,student['user_id'],date.today(),'ABSENT','MANUAL')
 record=db.attendance(student,course)[0];db.request_attendance_correction(student,record['attendance_id'],'PRESENT','I attended the class')
 request=db.correction_requests(teacher)[0]
 db.resolve_attendance_request(teacher,request['request_id'],True)
 assert db.attendance(student,course)[0]['status']=='PRESENT'
 assert db.correction_requests(student)[0]['status']=='APPROVED'
 for user in (admin,teacher,student):
  w=gui.MainWindow(user,gui.Login());w.show();app.processEvents()
  for i in range(w.tabs.count()):w.select_tab(i);app.processEvents()
  w.close()
 assert not errors,errors
 print('PASS: teacher approval, student request, teacher resolution and all role pages')
finally:c.rollback();c.close();print('Temporary records rolled back')

import os,uuid,contextlib
from datetime import date
import oracledb
from amrs import db
x=uuid.uuid4().hex[:8].upper();c=oracledb.connect(user='AMRS',password=os.environ['AMRS_DB_PASSWORD'],dsn='localhost:1521/FREEPDB1')
@contextlib.contextmanager
def shared():yield c
db.connection=shared
try:
 teacher_email='t'+x+'@example.test'; student_email='s'+x+'@example.test'; roll='T'+x
 db.signup_teacher('Temporary Teacher',teacher_email,'Testing-123','Software Engineering')
 db.signup_student('Temporary Student',student_email,'Testing-123',roll,1,1,2025)
 teacher=db.login('TEACHER',teacher_email,'Testing-123');student=db.login('STUDENT',roll,'Testing-123')
 db.add_course('T'+x,'Temporary Test',3,1,teacher['user_id'],1)
 course=db.one('SELECT course_id FROM courses WHERE course_code=:code',{'code':'T'+x})['course_id']
 db.enroll_student(course,student['user_id'])
 db.mark_attendance(teacher,course,student['user_id'],date.today(),'PRESENT','FACE',0.9)
 db.mark_attendance(teacher,course,student['user_id'],date.today(),'LATE','MANUAL')
 a=db.attendance(student,course);assert len(a)==1 and a[0]['status']=='LATE'
 db.correct_attendance(teacher,a[0]['attendance_id'],'ABSENT','Test correction');assert db.attendance(student,course)[0]['status']=='ABSENT'
 try:db.correct_attendance({'role':'TEACHER','user_id':'not-owner'},a[0]['attendance_id'],'PRESENT','Unauthorized')
 except ValueError:pass
 else:raise AssertionError('Unauthorized correction was accepted')
 summary=db.course_summary(teacher,course);assert len(summary)==1 and summary[0]['absent_count']==1
 stats=db.teacher_dashboard_stats(teacher['user_id']);assert stats['course_count']==1 and stats['student_count']==1 and stats['record_count']==1
 assert db.student_summary(student['user_id'])[0]['absent_count']==1
 db.mark_bulk(teacher,course,date.today(),[(student['user_id'],'PRESENT')]);assert db.attendance(student,course)[0]['status']=='PRESENT'
 db.request_reset('STUDENT',student_email,'Temporary Student','New-pass-123')
 req=db.one("SELECT request_id FROM password_reset_requests WHERE user_email=:email AND status='PENDING'",{'email':student_email.lower()})
 db.resolve_reset(req['request_id'],True);db.login('STUDENT',roll,'New-pass-123')
 print('PASS: teacher signup/login, student signup/login, course and enrollment, face/manual attendance upsert, report, password reset')
finally:c.rollback();c.close();print('Temporary database records rolled back')



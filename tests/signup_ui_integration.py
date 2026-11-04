import os,uuid,contextlib
import oracledb
from PySide6.QtCore import QEventLoop,QTimer
from PySide6.QtWidgets import QApplication,QWidget,QDialog
from amrs import gui,db
app=QApplication([]);x=uuid.uuid4().hex[:8].upper();c=oracledb.connect(user='AMRS',password=os.environ['AMRS_DB_PASSWORD'],dsn='localhost:1521/FREEPDB1')
@contextlib.contextmanager
def shared():yield c
db.connection=shared;errors=[];gui.error=lambda parent,e:errors.append(str(e));gui.alert=lambda *a:None
try:
 for role in ('TEACHER','STUDENT'):
  form=gui.Signup(None,role);email=role.lower()+x+'@example.test';form.name.setText('Temporary '+role);form.email.setText(email);form.password.setText('Testing-123');form.confirm.setText('Testing-123')
  if role=='STUDENT':form.roll.setText('T'+x)
  form.submit();assert form.result()==QDialog.DialogCode.Accepted and not errors,errors
  identity=('T'+x) if role=='STUDENT' else email
  if role=='TEACHER':
   adminrow=db.one("SELECT u.user_id FROM users u JOIN roles r ON r.role_id=u.role_id WHERE r.role_name='ADMIN' FETCH FIRST 1 ROWS ONLY");admin=dict(adminrow,role='ADMIN')
   try:db.login(role,identity,'Testing-123')
   except ValueError:pass
   else:raise AssertionError('Unapproved teacher signed in')
   request=next(r for r in db.pending_teacher_signups(admin) if r['email']==email.lower());db.resolve_teacher_signup(admin,request['request_id'],True)
  u=db.login(role,identity,'Testing-123');assert u['role']==role
  try:db.login(role,identity,'wrong-password')
  except ValueError:pass
  else:raise AssertionError('Wrong password was accepted')
  print(role,'UI signup and login: PASS')
 class TestMain(QWidget):
  def __init__(self,user,parent):super().__init__();self.user=user
 gui.MainWindow=TestMain;screen=gui.Login();screen.show();screen.select_role('STUDENT');screen.identity.setText('T'+x);screen.pw.setText('Testing-123');screen.login()
 loop=QEventLoop();QTimer.singleShot(2500,loop.quit);loop.exec()
 assert screen._login_task is None and hasattr(screen,'main') and screen.main.user['role']=='STUDENT' and not errors,errors
 print('Asynchronous Oracle login from desktop form: PASS')
 cur=c.cursor();cur.execute("INSERT INTO users (user_id,full_name,email,password_hash,role_id,is_active) VALUES(:id,'Temporary Admin',:email,:hash,(SELECT role_id FROM roles WHERE role_name='ADMIN'),1)",{'id':db.uid(),'email':'a'+x.lower()+'@example.test','hash':db.hash_password('Testing-123')})
 assert db.login('ADMIN','a'+x.lower()+'@example.test','Testing-123')['role']=='ADMIN'
 print('ADMIN fixed-credential authentication: PASS')
finally:c.rollback();c.close();print('Temporary authentication records rolled back')

"""Oracle data access for AMRS. No credentials are embedded in source."""
import os, uuid, threading, math, re, json, hashlib, copy
from contextlib import contextmanager
from datetime import date, datetime, timedelta
import bcrypt, oracledb

DSN=os.getenv('AMRS_ORACLE_DSN','localhost:1521/FREEPDB1')
_pool=None
_pool_lock=threading.Lock()
_read_context=threading.local()

class ReadSnapshotMiss(RuntimeError):
    """A presentation tried to read data that its background preload did not fetch."""

def _read_key(sql,params):
    normalized=re.sub(r'\s+',' ',sql).strip()
    values=[(str(k),type(v).__name__,str(v)) for k,v in sorted((params or {}).items())]
    return (normalized,hashlib.sha256(json.dumps(values,ensure_ascii=False).encode()).hexdigest())

@contextmanager
def capture_reads():
    previous=getattr(_read_context,'capture',None);snapshot={};_read_context.capture=snapshot
    try:yield snapshot
    finally:_read_context.capture=previous

@contextmanager
def use_reads(snapshot):
    previous=getattr(_read_context,'snapshot',None);_read_context.snapshot=snapshot
    try:yield
    finally:_read_context.snapshot=previous
def uid(): return str(uuid.uuid4())

def require_actor(user,roles=('ADMIN','TEACHER','STUDENT')):
    """Validate an in-process principal. Use session_is_active at action boundaries.

    A dictionary is not a network authentication token. The desktop currently runs
    in a trusted process; server-side signed sessions remain a deployment boundary.
    """
    if isinstance(roles,str):roles=(roles,)
    if not isinstance(user,dict) or user.get('role') not in roles or user.get('role') not in ('ADMIN','TEACHER','STUDENT'):
        raise ValueError('You are not authorized to perform this action.')
    if not isinstance(user.get('user_id'),str) or not 1<=len(user['user_id'])<=36:
        raise ValueError('A valid signed-in account is required.')
    return user

def session_is_active(user):
    require_actor(user)
    if user['role']=='STUDENT':
        return bool(one('''SELECT l.student_id FROM student_logins l JOIN students s ON s.student_id=l.student_id
            WHERE l.student_id=:id AND l.is_active=1 AND s.is_active=1''',{'id':user['user_id']}))
    return bool(one('''SELECT u.user_id FROM users u JOIN roles r ON r.role_id=u.role_id
        WHERE u.user_id=:id AND u.is_active=1 AND r.role_name=:role''',{'id':user['user_id'],'role':user['role']}))

def _active_actor(cur,user,roles=('ADMIN',)):
    require_actor(user,roles)
    if user['role']=='STUDENT':
        cur.execute('''SELECT COUNT(*) FROM student_logins l JOIN students s ON s.student_id=l.student_id
            WHERE l.student_id=:id AND l.is_active=1 AND s.is_active=1''',{'id':user['user_id']})
    else:
        cur.execute('''SELECT COUNT(*) FROM users u JOIN roles r ON r.role_id=u.role_id
            WHERE u.user_id=:id AND u.is_active=1 AND r.role_name=:role''',{'id':user['user_id'],'role':user['role']})
    if not cur.fetchone()[0]:raise ValueError('Your account is no longer active. Please sign in again.')

def audit_event(cur,user,action,entity_id='',detail=''):
    """Append a sanitized event within the caller's transaction; never commit here."""
    require_actor(user)
    if not isinstance(action,str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}',action):raise ValueError('Invalid audit action.')
    if len(str(entity_id))>64 or not isinstance(detail,str) or len(detail)>1000:raise ValueError('Audit event exceeds its permitted size.')
    cur.execute('''INSERT INTO app_audit(event_id,actor_id,actor_role,action,entity_id,detail)
        VALUES(:id,:actor,:role,:action,:entity,:detail)''',
        {'id':uid(),'actor':user['user_id'],'role':user['role'],'action':action,'entity':str(entity_id) or None,'detail':detail or None})

def _admin_action(cur,actor):
    if actor is not None:_active_actor(cur,actor)

def _admin_audit(cur,actor,action,entity_id):
    if actor is not None:audit_event(cur,actor,action,entity_id)

def _date_value(value,label='Attendance date'):
    if not isinstance(value,date) or isinstance(value,datetime):raise ValueError(label+' must be a date.')
    return value

def _date_range(start_date,end_date):
    if start_date is not None:_date_value(start_date,'Start date')
    if end_date is not None:_date_value(end_date,'End date')
    if start_date is not None and end_date is not None and start_date>end_date:raise ValueError('Start date must not be after end date.')

def _attendance_policy(cur=None):
    if cur is None:
        record=one("SELECT value_json FROM attendance_settings WHERE setting_key='ATTENDANCE_POLICY'")
        raw=record['value_json'] if record else None
    else:
        cur.execute("SELECT value_json FROM attendance_settings WHERE setting_key='ATTENDANCE_POLICY'")
        record=cur.fetchone();raw=record[0] if record else None
    policy={'minimum_percent':75,'editing_days':3,'late_counts_present':True}
    if raw:
        try:
            configured=json.loads(raw)
            if not isinstance(configured,dict) or set(configured)!=set(policy):raise ValueError()
            policy.update(configured)
            if isinstance(policy['minimum_percent'],bool) or not isinstance(policy['minimum_percent'],(int,float)) or not math.isfinite(policy['minimum_percent']) or not 0<=policy['minimum_percent']<=100:raise ValueError()
            if type(policy['editing_days']) is not int or not 0<=policy['editing_days']<=365:raise ValueError()
            if type(policy['late_counts_present']) is not bool:raise ValueError()
        except (ValueError,TypeError):raise ValueError('Attendance settings need administrator review.') from None
    return policy

def _check_edit_window(session_day,policy):
    day=session_day.date() if isinstance(session_day,datetime) else session_day
    if not isinstance(day,date) or not date.today()-timedelta(days=policy['editing_days'])<=day<=date.today():
        raise ValueError('The attendance editing window has closed. Contact your administrator.')

def _guard_manual_edits(cur,course_id,session_date,student_ids):
    # Today is always editable, including when editing_days is zero. Historical
    # initial entries remain supported; only an existing expired row is protected.
    if session_date==date.today():return
    policy=_attendance_policy(cur)
    if session_date>=date.today()-timedelta(days=policy['editing_days']):return
    cur.execute('''SELECT student_id FROM attendance WHERE course_id=:course AND session_date=:day FOR UPDATE WAIT 5''',
        {'course':course_id,'day':datetime.combine(session_date,datetime.min.time())})
    if set(student_ids).intersection(row[0] for row in cur):
        raise ValueError('The attendance editing window has closed. Contact your administrator.')
def get_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                from .config import load
                settings=load()
                schema=settings.db_schema
                if schema:
                    import re
                    if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,29}',schema):raise ValueError('Invalid Oracle schema setting.')
                def initialize_session(conn,requested_tag):
                    conn.call_timeout=10000
                    if schema:conn.cursor().execute('ALTER SESSION SET CURRENT_SCHEMA='+schema)
                _pool=oracledb.create_pool(user=settings.db_username,password=os.environ['AMRS_DB_PASSWORD'],dsn=settings.db_dsn,min=settings.pool_min,max=settings.pool_max,increment=1,getmode=oracledb.POOL_GETMODE_TIMEDWAIT,wait_timeout=10000,tcp_connect_timeout=5,retry_count=0,session_callback=initialize_session)
    return _pool
@contextmanager
def connection():
    c=get_pool().acquire()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback(); raise
    finally: c.close()
def rows(sql,params=None):
    key=_read_key(sql,params);snapshot=getattr(_read_context,'snapshot',None)
    if snapshot is not None:
        if key not in snapshot:raise ReadSnapshotMiss('The screen needs a background data refresh before it can open.')
        return copy.deepcopy(snapshot[key])
    with connection() as c:
        cur=c.cursor();cur.execute(sql,params or {}); names=[v[0].lower() for v in cur.description]
        result=[dict(zip(names,row)) for row in cur]
    capture=getattr(_read_context,'capture',None)
    if capture is not None:capture[key]=copy.deepcopy(result)
    return result
def one(sql,params=None):
    v=rows(sql,params);return v[0] if v else None
def hash_password(password):
    if len(password)<8: raise ValueError('Password must be at least 8 characters.')
    if len(password.encode())>72: raise ValueError('Password is too long (maximum 72 bytes).')
    return bcrypt.hashpw(password.encode(),bcrypt.gensalt(rounds=12)).decode()
def check_password(password,stored):
    try:return bcrypt.checkpw(password.encode(),stored.encode())
    except (ValueError,TypeError):return False

def login(role,identity,password):
    if role not in ('ADMIN','TEACHER','STUDENT'):raise ValueError('Invalid login role.')
    if not isinstance(identity,str) or not identity.strip() or not isinstance(password,str):raise ValueError('Enter your login and password.')
    if role=='STUDENT':
        r=one('''SELECT l.student_id user_id,l.email,s.full_name,l.password_hash FROM student_logins l
                 JOIN students s ON s.student_id=l.student_id WHERE l.is_active=1 AND s.is_active=1
                 AND (LOWER(l.email)=LOWER(:identity) OR LOWER(s.roll_number)=LOWER(:identity))''',{'identity':identity.strip()})
    else:
        r=one('''SELECT u.user_id,u.email,u.full_name,u.password_hash FROM users u JOIN roles r ON r.role_id=u.role_id
                 WHERE u.is_active=1 AND r.role_name=:role AND LOWER(u.email)=LOWER(:identity)''',{'role':role,'identity':identity.strip()})
    if not r or not check_password(password,r['password_hash']):raise ValueError('Invalid username or password.')
    r.pop('password_hash');r['role']=role;return r

def departments():return rows('SELECT dept_id,dept_name FROM departments ORDER BY dept_id')
def signup_teacher(name,email,password,department,*,actor=None):
    if not name.strip() or '@' not in email: raise ValueError('Enter a name and valid email.')
    pw=hash_password(password);teacher_id=uid()
    with connection() as c:
        cur=c.cursor();_admin_action(cur,actor);cur.execute('''INSERT INTO users (user_id,full_name,email,password_hash,role_id,department,is_active)
             VALUES (:id,:name,:email,:pw,(SELECT role_id FROM roles WHERE role_name='TEACHER'),:dept,1)''',
             {'id':teacher_id,'name':name.strip(),'email':email.strip().lower(),'pw':pw,'dept':department})
        _admin_audit(cur,actor,'TEACHER_CREATED',teacher_id)
def signup_student(name,email,password,roll,dept,semester,year):
    if not name.strip() or '@' not in email or not roll.strip(): raise ValueError('Enter name, roll number and valid email.')
    pw=hash_password(password);roll=roll.strip().upper()
    with connection() as c:
        cur=c.cursor();cur.execute('SELECT student_id,is_active FROM students WHERE UPPER(roll_number)=:roll AND is_active=1',{'roll':roll});old=cur.fetchone()
        if old:
            sid=old[0];cur.execute('SELECT COUNT(*) FROM student_logins WHERE student_id=:sid',{'sid':sid})
            if cur.fetchone()[0]: raise ValueError('This student already has a login account.')
            # Do not allow someone to claim an existing student using just a roll number.
            raise ValueError('Existing student records need an administrator to create the login.')
        cur.execute('SELECT COUNT(*) FROM students WHERE is_active=1 AND LOWER(email)=LOWER(:email)',{'email':email.strip()})
        if cur.fetchone()[0]:raise ValueError('An active student already uses this email.')
        cur.execute('SELECT COUNT(*) FROM student_logins l JOIN students s ON s.student_id=l.student_id WHERE s.is_active=1 AND LOWER(l.email)=LOWER(:email)',{'email':email.strip()})
        if cur.fetchone()[0]:raise ValueError('An active student login already uses this email.')
        sid=uid();cur.execute('''INSERT INTO students(student_id,roll_number,full_name,email,dept_id,semester,batch_year,is_active,face_enrolled)
             VALUES(:id,:roll,:name,:email,:dept,:sem,:year,1,0)''',{'id':sid,'roll':roll,'name':name.strip(),'email':email.strip().lower(),'dept':dept,'sem':semester,'year':year})
        cur.execute('INSERT INTO student_logins(login_id,student_id,email,password_hash,is_active) VALUES(:id,:sid,:email,:pw,1)',{'id':uid(),'sid':sid,'email':email.strip().lower(),'pw':pw})

def students():return rows('''SELECT s.student_id,s.roll_number,s.full_name,s.email,s.semester,s.batch_year,s.face_enrolled,d.dept_name FROM students s JOIN departments d ON d.dept_id=s.dept_id WHERE s.is_active=1 ORDER BY s.roll_number''')
def teachers():return rows("SELECT u.user_id,u.full_name,u.email,u.department FROM users u JOIN roles r ON r.role_id=u.role_id WHERE r.role_name='TEACHER' AND u.is_active=1 ORDER BY u.full_name")
def courses(user=None):
    if user is not None:require_actor(user)
    if user and user['role']=='TEACHER':return rows('SELECT course_id,course_code,course_name FROM courses WHERE is_active=1 AND teacher_id=:id ORDER BY course_code',{'id':user['user_id']})
    if user and user['role']=='STUDENT':return rows('SELECT c.course_id,c.course_code,c.course_name FROM courses c JOIN course_enrollments e ON e.course_id=c.course_id WHERE e.student_id=:id AND c.is_active=1 ORDER BY c.course_code',{'id':user['user_id']})
    return rows('''SELECT c.course_id,c.course_code,c.course_name,c.semester,c.credit_hours,u.full_name teacher_name,d.dept_name FROM courses c JOIN users u ON u.user_id=c.teacher_id JOIN departments d ON d.dept_id=c.dept_id WHERE c.is_active=1 ORDER BY c.course_code''')
def course_students(course_id):
    return rows('''SELECT s.student_id,s.roll_number,s.full_name,s.face_enrolled FROM students s JOIN course_enrollments e
                ON e.student_id=s.student_id WHERE e.course_id=:id AND s.is_active=1 ORDER BY s.roll_number''',{'id':course_id})
def authorized_course_students(user,course_id):
    require_actor(user,('ADMIN','TEACHER'))
    if not session_is_active(user):raise ValueError('Your account is no longer active. Please sign in again.')
    if user['role']=='TEACHER' and not one('SELECT course_id FROM courses WHERE course_id=:course AND teacher_id=:teacher AND is_active=1',{'course':course_id,'teacher':user['user_id']}):
        raise ValueError('Course is not assigned to you.')
    return course_students(course_id)

def attendance(user,course_id=None,start_date=None,end_date=None):
    require_actor(user);_date_range(start_date,end_date)
    query='''SELECT a.attendance_id,a.course_id,a.student_id,a.session_date,c.course_code,s.roll_number,s.full_name,a.status,a.check_in_method,a.remarks FROM attendance a
    JOIN courses c ON c.course_id=a.course_id JOIN students s ON s.student_id=a.student_id WHERE 1=1''';p={}
    if user['role']=='STUDENT':query+=' AND a.student_id=:student';p['student']=user['user_id']
    elif user['role']=='TEACHER':query+=' AND c.teacher_id=:teacher';p['teacher']=user['user_id']
    if course_id:query+=' AND a.course_id=:course';p['course']=course_id
    if start_date is not None:query+=' AND a.session_date>=:start_day';p['start_day']=datetime.combine(start_date,datetime.min.time())
    if end_date is not None:query+=' AND TRUNC(a.session_date)<=:end_day';p['end_day']=datetime.combine(end_date,datetime.min.time())
    return rows(query+' ORDER BY a.session_date DESC,s.roll_number',p)
UPSERT_ATTENDANCE="""MERGE INTO attendance a USING (SELECT :course course_id,:student student_id,:teacher teacher_id,:day session_date,
          :status status,:method method,:score score FROM dual) x ON (a.course_id=x.course_id AND a.student_id=x.student_id AND a.session_date=x.session_date)
          WHEN MATCHED THEN UPDATE SET a.status=x.status,a.check_in_method=x.method,a.face_match_score=x.score
          WHERE x.method='MANUAL'
          WHEN NOT MATCHED THEN INSERT (course_id,student_id,teacher_id,session_date,status,check_in_method,face_match_score)
          VALUES(x.course_id,x.student_id,x.teacher_id,x.session_date,x.status,x.method,x.score)"""
def session_attendance(user,course_id,session_date):
    require_actor(user,('TEACHER',));_date_value(session_date)
    return rows("""SELECT a.student_id,a.status,a.check_in_method,a.updated_at FROM attendance a JOIN courses c ON c.course_id=a.course_id
        WHERE a.course_id=:course AND c.teacher_id=:teacher AND a.session_date=:day""",
        {'course':course_id,'teacher':user['user_id'],'day':datetime.combine(session_date,datetime.min.time())})
def _mark(cur,user,course_id,student_id,session_date,status,method,score):
    require_actor(user,('TEACHER',));_date_value(session_date)
    if status not in ('PRESENT','ABSENT','LATE') or method not in ('MANUAL','QR','FACE'):raise ValueError('Invalid attendance request.')
    if method!='MANUAL' and status not in ('PRESENT','LATE'):raise ValueError('Automated check-in cannot mark absence.')
    if method=='FACE':
        from .config import load
        threshold=load().face_threshold
        if not math.isfinite(threshold) or not 0<threshold<=1:raise ValueError('Invalid configured face confidence threshold.')
        if isinstance(score,bool) or not isinstance(score,(int,float)) or not math.isfinite(score) or not threshold<=score<=1:
            raise ValueError('Face confidence is below the required threshold or invalid.')
    elif score is not None:raise ValueError('A face confidence score is only valid for face attendance.')
    if session_date>date.today():raise ValueError('Future attendance is not allowed.')
    cur.execute("""SELECT COUNT(*) FROM courses c JOIN course_enrollments e ON e.course_id=c.course_id
         JOIN students s ON s.student_id=e.student_id JOIN users u ON u.user_id=c.teacher_id JOIN roles r ON r.role_id=u.role_id
         WHERE c.course_id=:course AND c.teacher_id=:teacher AND c.is_active=1 AND u.is_active=1 AND r.role_name='TEACHER'
         AND s.student_id=:student AND s.is_active=1""",{'course':course_id,'teacher':user['user_id'],'student':student_id})
    if not cur.fetchone()[0]:raise ValueError('Student is not enrolled in this teacher’s active course.')
    params={'course':course_id,'student':student_id,'teacher':user['user_id'],'day':datetime.combine(session_date,datetime.min.time()),'status':status,'method':method,'score':score}
    if method=='MANUAL':_guard_manual_edits(cur,course_id,session_date,[student_id])
    try:cur.execute(UPSERT_ATTENDANCE,params)
    except oracledb.IntegrityError as exc:
        # Concurrent QR and face check-ins may race on the same unique session key.
        if not exc.args or getattr(exc.args[0],'code',None)!=1:raise
        # Recheck after a competing historical insertion wins the unique-key race.
        if method=='MANUAL':_guard_manual_edits(cur,course_id,session_date,[student_id])
        cur.execute("""UPDATE attendance SET status=:status,check_in_method=:method,face_match_score=:score
            WHERE course_id=:course AND student_id=:student AND session_date=:day AND :method='MANUAL'""",
            {k:params[k] for k in ('status','method','score','course','student','day')})
        if cur.rowcount not in (0,1):raise
    if cur.rowcount==0:
        cur.execute('SELECT status FROM attendance WHERE course_id=:course AND student_id=:student AND session_date=:day',
            {k:params[k] for k in ('course','student','day')})
        existing=cur.fetchone()
        if not existing or existing[0] not in ('PRESENT','LATE'):
            raise ValueError('Attendance is already recorded with a different result. Ask the teacher to review it manually.')
        return False
    return True

def mark_attendance(user,course_id,student_id,session_date,status='PRESENT',method='MANUAL',score=None):
    with connection() as c:
        cur=c.cursor();changed=_mark(cur,user,course_id,student_id,session_date,status,method,score)
        if changed:audit_event(cur,user,'ATTENDANCE_RECORDED',course_id,f'student={student_id}; date={session_date.isoformat()}; status={status}; method={method}')
        return changed


def qr_face_student(course_id, student_id):
    return one("""SELECT s.student_id,s.roll_number,s.face_enrolled FROM students s
        JOIN course_enrollments e ON e.student_id=s.student_id
        JOIN student_logins l ON l.student_id=s.student_id
        JOIN biometric_consents b ON b.student_id=s.student_id
        WHERE e.course_id=:course AND s.student_id=:student AND s.is_active=1
        AND l.is_active=1 AND s.face_enrolled=1 AND b.consent_given=1""",
        {'course':course_id,'student':student_id})


def mark_verified_qr(user, course_id, student_id, session_date, token):
    """Save only through the QR server's verified ticket, with current Oracle checks."""
    require_actor(user, ('TEACHER',))
    with connection() as c:
        cur = c.cursor()
        cur.execute("""SELECT 1 FROM checkin_sessions WHERE session_token=:token
            AND course_id=:course AND teacher_id=:teacher AND session_date=:day
            AND expires_at>CAST(SYSDATE AS TIMESTAMP)""",
            {'token':token,'course':course_id,'teacher':user['user_id'],
             'day':datetime.combine(session_date,datetime.min.time())})
        if not cur.fetchone():
            raise ValueError('This QR session has ended.')
        cur.execute("""SELECT b.consent_given FROM biometric_consents b
            JOIN students s ON s.student_id=b.student_id
            JOIN student_logins l ON l.student_id=b.student_id
            WHERE b.student_id=:student AND s.is_active=1 AND s.face_enrolled=1
            AND l.is_active=1 FOR UPDATE OF b.consent_given WAIT 5""", {'student':student_id})
        if cur.fetchone() != (1,):
            raise ValueError('Face enrollment or consent is no longer active.')
        changed = _mark(cur,user,course_id,student_id,session_date,'PRESENT','QR',None)
        if changed:
            audit_event(cur,user,'ATTENDANCE_RECORDED',course_id,
                f'student={student_id}; date={session_date.isoformat()}; status=PRESENT; method=QR')
        return changed


def mark_bulk(user,course_id,session_date,entries,expected=None):
    require_actor(user,('TEACHER',));_date_value(session_date)
    if session_date>date.today():raise ValueError('Future attendance is not allowed.')
    if not entries:raise ValueError('No attendance entries to save.')
    ids=[sid for sid,_ in entries]
    if len(ids)!=len(set(ids)) or any(status not in ('PRESENT','ABSENT','LATE') for _,status in entries):raise ValueError('Invalid attendance entries.')
    with connection() as c:
        cur=c.cursor();cur.execute("""SELECT s.student_id FROM courses c JOIN course_enrollments e ON e.course_id=c.course_id
            JOIN students s ON s.student_id=e.student_id JOIN users u ON u.user_id=c.teacher_id JOIN roles r ON r.role_id=u.role_id
            WHERE c.course_id=:course AND c.teacher_id=:teacher AND c.is_active=1 AND s.is_active=1 AND u.is_active=1 AND r.role_name='TEACHER'""",
            {'course':course_id,'teacher':user['user_id']})
        enrolled={r[0] for r in cur}
        if not set(ids).issubset(enrolled):raise ValueError('A student is not enrolled in this teacher’s active course.')
        _guard_manual_edits(cur,course_id,session_date,ids)
        day=datetime.combine(session_date,datetime.min.time())
        if expected is not None:
            if not set(ids).issubset(expected):raise ValueError('Attendance snapshot is incomplete. Reload the class.')
            cur.execute('SELECT student_id,status,check_in_method,updated_at FROM attendance WHERE course_id=:course AND session_date=:day FOR UPDATE WAIT 5',{'course':course_id,'day':day})
            current={row[0]:(row[1],row[2],row[3]) for row in cur}
            if any(current.get(sid)!=expected[sid] for sid in ids):raise ValueError('Attendance changed after loading. Reload students before saving.')
        cur.executemany(UPSERT_ATTENDANCE,[{'course':course_id,'student':sid,'teacher':user['user_id'],'day':day,'status':status,'method':'MANUAL','score':None} for sid,status in entries])
        for sid,status in entries:audit_event(cur,user,'ATTENDANCE_MANUAL',course_id,f'student={sid}; date={session_date.isoformat()}; status={status}')
def enroll_student(course,student,*,actor=None):
    with connection() as c:
        cur=c.cursor();_admin_action(cur,actor);cur.execute('INSERT INTO course_enrollments(course_id,student_id) VALUES(:course,:student)',{'course':course,'student':student})
        _admin_audit(cur,actor,'STUDENT_ENROLLED',course)
def add_course(code,name,credits,dept,teacher,semester,*,actor=None):
    if not code.strip() or not name.strip():raise ValueError('Course code and name are required.')
    course_id=uid()
    with connection() as c:
        cur=c.cursor();_admin_action(cur,actor);cur.execute('''INSERT INTO courses(course_id,course_code,course_name,credit_hours,dept_id,teacher_id,semester,is_active)
        VALUES(:id,:code,:name,:credits,:dept,:teacher,:semester,1)''',{'id':course_id,'code':code.strip().upper(),'name':name.strip(),'credits':credits,'dept':dept,'teacher':teacher,'semester':semester})
        _admin_audit(cur,actor,'COURSE_CREATED',course_id)
def set_face_enrolled(student_id):
    with connection() as c:
        cur=c.cursor();cur.execute('UPDATE students SET face_enrolled=1 WHERE student_id=:id AND is_active=1',{'id':student_id})
        if cur.rowcount!=1:raise ValueError('Student is not active.')
def create_student_login(student_id,email,password,*,actor=None):
    if '@' not in email:raise ValueError('Enter a valid email.')
    with connection() as c:
        cur=c.cursor();_admin_action(cur,actor);cur.execute('SELECT COUNT(*) FROM student_logins WHERE student_id=:id',{'id':student_id})
        if cur.fetchone()[0]:raise ValueError('Student already has a login.')
        cur.execute('SELECT COUNT(*) FROM student_logins WHERE LOWER(email)=LOWER(:email)',{'email':email.strip()})
        if cur.fetchone()[0]:raise ValueError('This login email is already in use.')
        cur.execute('INSERT INTO student_logins(login_id,student_id,email,password_hash,is_active) VALUES(:id,:student,:email,:pw,1)',{'id':uid(),'student':student_id,'email':email.strip().lower(),'pw':hash_password(password)})
        _admin_audit(cur,actor,'STUDENT_LOGIN_CREATED',student_id)
def request_reset(role,email,name,password):
    if role not in ('TEACHER','STUDENT') or not name.strip():raise ValueError('Please enter your name.')
    if role=='TEACHER':u=one("SELECT u.user_id FROM users u JOIN roles r ON r.role_id=u.role_id WHERE r.role_name='TEACHER' AND LOWER(u.email)=LOWER(:email)",{'email':email.strip()})
    else:u=one('SELECT student_id user_id FROM student_logins WHERE LOWER(email)=LOWER(:email)',{'email':email.strip()})
    if not u:raise ValueError('Account not found.')
    with connection() as c:c.cursor().execute('''INSERT INTO password_reset_requests(request_id,user_type,user_id,user_email,user_name,new_password_hash,status)
    VALUES(:id,:role,:user_id,:email,:name,:pw,'PENDING')''',{'id':uid(),'role':role,'user_id':u['user_id'],'email':email.strip().lower(),'name':name.strip(),'pw':hash_password(password)})
def pending_resets():return rows("SELECT request_id,user_type,user_name,user_email,requested_at FROM password_reset_requests WHERE status='PENDING' ORDER BY requested_at")
def resolve_reset(request_id,approve,*,actor=None):
    with connection() as c:
        cur=c.cursor();_admin_action(cur,actor);cur.execute("SELECT user_type,user_id,new_password_hash FROM password_reset_requests WHERE request_id=:id AND status='PENDING' FOR UPDATE",{'id':request_id});r=cur.fetchone()
        if not r:raise ValueError('Request not found or already resolved.')
        if approve:
            target='users' if r[0]=='TEACHER' else 'student_logins';col='user_id' if r[0]=='TEACHER' else 'student_id'
            cur.execute('UPDATE '+target+' SET password_hash=:pw WHERE '+col+'=:id',{'pw':r[2],'id':r[1]})
            if cur.rowcount!=1:raise ValueError('User account is missing.')
        cur.execute('UPDATE password_reset_requests SET status=:status,resolved_at=CURRENT_TIMESTAMP WHERE request_id=:id',{'status':'APPROVED' if approve else 'REJECTED','id':request_id})
        _admin_audit(cur,actor,'LEGACY_RESET_APPROVED' if approve else 'LEGACY_RESET_REJECTED',request_id)
def add_student(name,roll,email,phone,dept,semester,year,*,actor=None):
    if not name.strip() or not roll.strip():raise ValueError('Name and roll number are required.')
    student_id=uid()
    with connection() as c:
        cur=c.cursor();_admin_action(cur,actor)
        if email.strip():
            cur.execute('SELECT COUNT(*) FROM students WHERE is_active=1 AND LOWER(email)=LOWER(:email)',{'email':email.strip()})
            if cur.fetchone()[0]:raise ValueError('An active student already uses this email.')
            cur.execute('SELECT COUNT(*) FROM student_logins l JOIN students s ON s.student_id=l.student_id WHERE s.is_active=1 AND LOWER(l.email)=LOWER(:email)',{'email':email.strip()})
            if cur.fetchone()[0]:raise ValueError('An active student login already uses this email.')
        cur.execute('''INSERT INTO students(student_id,roll_number,full_name,email,phone,dept_id,semester,batch_year,is_active,face_enrolled)
      VALUES(:id,:roll,:name,:email,:phone,:dept,:sem,:year,1,0)''',{'id':student_id,'roll':roll.strip().upper(),'name':name.strip(),'email':email.strip() or None,'phone':phone.strip() or None,'dept':dept,'sem':semester,'year':year})
        _admin_audit(cur,actor,'STUDENT_CREATED',student_id)
    return student_id
def update_student(student_id,name,email,phone,dept,semester,year,*,actor=None):
    if not name.strip():raise ValueError('Name is required.')
    with connection() as c:
        cur=c.cursor();_admin_action(cur,actor);cur.execute('''UPDATE students SET full_name=:name,email=:email,phone=:phone,dept_id=:dept,semester=:sem,batch_year=:year WHERE student_id=:id''',{'id':student_id,'name':name.strip(),'email':email.strip() or None,'phone':phone.strip() or None,'dept':dept,'sem':semester,'year':year})
        if cur.rowcount!=1:raise ValueError('Student not found.')
        _admin_audit(cur,actor,'STUDENT_UPDATED',student_id)
def update_admin_profile(user, name, email, current_password):
    from .mail_delivery import valid_email

    require_actor(user, ('ADMIN',))
    name = name.strip()
    if not name or len(name.encode('utf-8')) > 200:
        raise ValueError('Enter a name between 1 and 200 bytes.')
    email = valid_email(email)
    if len(email.encode('utf-8')) > 255:
        raise ValueError('Enter a shorter email address.')
    with connection() as c:
        cur = c.cursor()
        cur.execute(
            """SELECT full_name,email,password_hash FROM users
            WHERE user_id=:id AND is_active=1
            AND role_id=(SELECT role_id FROM roles WHERE role_name='ADMIN')
            FOR UPDATE WAIT 5""",
            {'id': user['user_id']},
        )
        row = cur.fetchone()
        if not row or row[:2] != (user['full_name'], user['email']):
            raise ValueError('Your profile changed or is no longer active. Sign in again.')
        email_changed = email != row[1]
        if (name, email) == row[:2]:
            return name, email
        if email_changed:
            if not current_password or not check_password(current_password, row[2]):
                raise ValueError('Enter your current password to change your login email.')
            cur.execute(
                'SELECT 1 FROM users WHERE LOWER(email)=:email AND user_id<>:id',
                {'email': email, 'id': user['user_id']},
            )
            if cur.fetchone():
                raise ValueError('This email is already used by another account.')
        try:
            cur.execute(
                'UPDATE users SET full_name=:name,email=:email WHERE user_id=:id',
                {'name': name, 'email': email, 'id': user['user_id']},
            )
        except oracledb.IntegrityError as exc:
            if exc.args[0].code == 1:
                raise ValueError('This email is already used by another account.') from None
            raise
        audit_event(
            cur, user, 'ADMIN_EMAIL_CHANGED' if email_changed else 'ADMIN_NAME_CHANGED',
            user['user_id'],
        )
    return name, email


def change_password(user,old,new):
    authenticated=login(user['role'],user['email'],old)
    if authenticated['user_id']!=user['user_id']:raise ValueError('Account identity does not match the signed-in user.')
    value=hash_password(new)
    table='student_logins' if user['role']=='STUDENT' else 'users';col='student_id' if user['role']=='STUDENT' else 'user_id'
    with connection() as c:
        cur=c.cursor();cur.execute('UPDATE '+table+' SET password_hash=:pw WHERE '+col+'=:id',{'pw':value,'id':user['user_id']})
        if cur.rowcount!=1:raise ValueError('Account is no longer available.')
        audit_event(cur,user,'PASSWORD_CHANGED',user['user_id'])
def update_course(course_id,code,name,credits,dept,teacher,semester,*,actor=None):
    if not code.strip() or not name.strip():raise ValueError('Code and name are required.')
    with connection() as c:
        cur=c.cursor();_admin_action(cur,actor);cur.execute('''UPDATE courses SET course_code=:code,course_name=:name,credit_hours=:credits,dept_id=:dept,
        teacher_id=:teacher,semester=:semester WHERE course_id=:id''',{'id':course_id,'code':code.strip().upper(),'name':name.strip(),'credits':credits,'dept':dept,'teacher':teacher,'semester':semester})
        if cur.rowcount!=1:raise ValueError('Course not found.')
        _admin_audit(cur,actor,'COURSE_UPDATED',course_id)
def update_teacher(teacher_id,name,department,*,actor=None):
    if not name.strip():raise ValueError('Name is required.')
    with connection() as c:
        cur=c.cursor();_admin_action(cur,actor);cur.execute("UPDATE users SET full_name=:name,department=:dept WHERE user_id=:id AND role_id=(SELECT role_id FROM roles WHERE role_name='TEACHER')",{'id':teacher_id,'name':name.strip(),'dept':department})
        if cur.rowcount!=1:raise ValueError('Teacher not found.')
        _admin_audit(cur,actor,'TEACHER_UPDATED',teacher_id)
def unenroll_student(course,student,*,actor=None):
    with connection() as c:
        cur=c.cursor();_admin_action(cur,actor);cur.execute('DELETE FROM course_enrollments WHERE course_id=:course AND student_id=:student',{'course':course,'student':student})
        _admin_audit(cur,actor,'STUDENT_UNENROLLED',course)

def enroll_all_students(course_id,*,actor=None):
    if not course_id:raise ValueError('Select a course first.')
    with connection() as c:
        cur=c.cursor();_admin_action(cur,actor);cur.execute("SELECT COUNT(*) FROM courses WHERE course_id=:id AND is_active=1",{'id':course_id})
        if not cur.fetchone()[0]:raise ValueError('Course not found.')
        cur.execute("""INSERT INTO course_enrollments(course_id,student_id)
            SELECT :course,s.student_id FROM students s JOIN courses c ON c.course_id=:course
            WHERE s.is_active=1 AND s.dept_id=c.dept_id AND s.semester=c.semester AND NOT EXISTS
            (SELECT 1 FROM course_enrollments e WHERE e.course_id=:course AND e.student_id=s.student_id)""",{'course':course_id})
        count=cur.rowcount;_admin_audit(cur,actor,'MATCHING_STUDENTS_ENROLLED',course_id)
        return count

def correct_attendance(user,attendance_id,status,remarks):
    require_actor(user,('TEACHER',))
    if status not in ('PRESENT','ABSENT','LATE'):raise ValueError('Invalid correction request.')
    if not remarks.strip() or len(remarks.strip())>1000:raise ValueError('Please enter a reason of up to 1000 characters for the correction.')
    with connection() as c:
        cur=c.cursor();_active_actor(cur,user,('TEACHER',));policy=_attendance_policy(cur)
        cur.execute('''SELECT a.status,a.session_date FROM attendance a JOIN courses c ON c.course_id=a.course_id
            WHERE a.attendance_id=:id AND c.teacher_id=:teacher AND c.is_active=1 FOR UPDATE OF a.status''',
            {'id':attendance_id,'teacher':user['user_id']});old=cur.fetchone()
        if not old:raise ValueError('Attendance record not found in your active courses.')
        _check_edit_window(old[1],policy)
        cur.execute('UPDATE attendance SET status=:status,remarks=:remarks WHERE attendance_id=:id',
            {'status':status,'remarks':remarks.strip(),'id':attendance_id})
        if cur.rowcount!=1:raise ValueError('Attendance record not found in your courses.')
        audit_event(cur,user,'ATTENDANCE_CORRECTED',attendance_id,f'old_status={old[0]}; new_status={status}; reason_recorded=True')
def _summary_source(where):
    return '''SELECT course_id,student_id,COUNT(*) total_sessions,
        SUM(CASE WHEN status='PRESENT' THEN 1 ELSE 0 END) present_count,
        SUM(CASE WHEN status='ABSENT' THEN 1 ELSE 0 END) absent_count,
        SUM(CASE WHEN status='LATE' THEN 1 ELSE 0 END) late_count,
        ROUND(100*SUM(CASE WHEN status='PRESENT' OR (status='LATE' AND :late_counts=1) THEN 1 ELSE 0 END)/COUNT(*),2) attendance_pct
        FROM attendance WHERE '''+where+' GROUP BY course_id,student_id'

def _summary_policy(results,policy):
    for record in results:
        record['minimum_percent']=policy['minimum_percent']
        record['meets_minimum']=record['total_sessions']>0 and float(record['attendance_pct'])>=policy['minimum_percent']
    return results

def course_summary(user,course_id,start_date=None,end_date=None):
    require_actor(user,('ADMIN','TEACHER'));_date_range(start_date,end_date)
    if user['role']=='TEACHER' and not one('SELECT course_id FROM courses WHERE course_id=:id AND teacher_id=:teacher',{'id':course_id,'teacher':user['user_id']}):raise ValueError('Course is not assigned to you.')
    policy=_attendance_policy();where='course_id=:course';params={'course':course_id,'late_counts':int(policy['late_counts_present'])}
    if start_date is not None:where+=' AND session_date>=:start_day';params['start_day']=datetime.combine(start_date,datetime.min.time())
    if end_date is not None:where+=' AND TRUNC(session_date)<=:end_day';params['end_day']=datetime.combine(end_date,datetime.min.time())
    result=rows("""SELECT s.roll_number,s.full_name,COALESCE(v.total_sessions,0) total_sessions,COALESCE(v.present_count,0) present_count,
        COALESCE(v.absent_count,0) absent_count,COALESCE(v.late_count,0) late_count,COALESCE(v.attendance_pct,0) attendance_pct
        FROM course_enrollments e JOIN students s ON s.student_id=e.student_id
        LEFT JOIN ("""+_summary_source(where)+""") v ON v.course_id=e.course_id AND v.student_id=e.student_id
        WHERE e.course_id=:course AND s.is_active=1 ORDER BY s.roll_number""",params)
    return _summary_policy(result,policy)

def student_summary(student_id,user=None):
    if user is not None:
        require_actor(user,('ADMIN','STUDENT'))
        if user['role']=='STUDENT' and user['user_id']!=student_id:raise ValueError('You can only view your own attendance summary.')
    policy=_attendance_policy()
    result=rows("""SELECT c.course_code,c.course_name,COALESCE(v.total_sessions,0) total_sessions,COALESCE(v.present_count,0) present_count,
        COALESCE(v.absent_count,0) absent_count,COALESCE(v.late_count,0) late_count,COALESCE(v.attendance_pct,0) attendance_pct
        FROM course_enrollments e JOIN courses c ON c.course_id=e.course_id
        LEFT JOIN ("""+_summary_source('student_id=:student')+""") v ON v.course_id=e.course_id AND v.student_id=e.student_id
        WHERE e.student_id=:student AND c.is_active=1 ORDER BY c.course_code""",{'student':student_id,'late_counts':int(policy['late_counts_present'])})
    return _summary_policy(result,policy)


def delete_student_permanently(student_id,*,actor=None):
    with connection() as c:
        cur=c.cursor();_admin_action(cur,actor);cur.execute("DELETE FROM password_reset_requests WHERE user_type='STUDENT' AND user_id=:id",{'id':student_id})
        cur.execute('DELETE FROM students WHERE student_id=:id',{'id':student_id})
        if cur.rowcount!=1:raise ValueError('Student not found.')
        _admin_audit(cur,actor,'STUDENT_DELETED',student_id)

def teacher_dashboard_stats(teacher_id,user=None):
    if user is not None:
        require_actor(user,('ADMIN','TEACHER'))
        if user['role']=='TEACHER' and user['user_id']!=teacher_id:raise ValueError('You can only view your own dashboard.')
    return one("""SELECT
        (SELECT COUNT(*) FROM courses WHERE teacher_id=:teacher AND is_active=1) course_count,
        (SELECT COUNT(DISTINCT e.student_id) FROM course_enrollments e JOIN courses c ON c.course_id=e.course_id
         JOIN students s ON s.student_id=e.student_id WHERE c.teacher_id=:teacher AND c.is_active=1 AND s.is_active=1) student_count,
        (SELECT COUNT(*) FROM attendance a JOIN courses c ON c.course_id=a.course_id WHERE c.teacher_id=:teacher) record_count
        FROM dual""",{'teacher':teacher_id})


def request_teacher_signup(name,email,password,department):
    if not name.strip() or '@' not in email:raise ValueError('Enter a name and valid email.')
    email=email.strip().lower();pw=hash_password(password)
    with connection() as c:
        cur=c.cursor();cur.execute("SELECT is_active FROM users WHERE LOWER(email)=:email",{'email':email});existing=cur.fetchone()
        if existing:raise ValueError('An account already uses this email.')
        cur.execute("SELECT COUNT(*) FROM teacher_signup_requests WHERE LOWER(email)=:email AND status='PENDING'",{'email':email})
        if cur.fetchone()[0]:raise ValueError('A request for this email is already pending.')
        cur.execute("INSERT INTO teacher_signup_requests(request_id,full_name,email,password_hash,department) VALUES(:id,:name,:email,:pw,:dept)",{'id':uid(),'name':name.strip(),'email':email,'pw':pw,'dept':department})

def pending_teacher_signups(user):
    require_actor(user,('ADMIN',))
    return rows("SELECT request_id,full_name,email,department,created_at FROM teacher_signup_requests WHERE status='PENDING' ORDER BY created_at")

def resolve_teacher_signup(user,request_id,approve):
    require_actor(user,('ADMIN',))
    with connection() as c:
        cur=c.cursor();_active_actor(cur,user);cur.execute("SELECT full_name,email,password_hash,department FROM teacher_signup_requests WHERE request_id=:id AND status='PENDING' FOR UPDATE WAIT 5",{'id':request_id});r=cur.fetchone()
        if not r:raise ValueError('Request is no longer pending.')
        if approve:
            cur.execute("INSERT INTO users(user_id,full_name,email,password_hash,role_id,department,is_active) VALUES(:id,:name,:email,:pw,(SELECT role_id FROM roles WHERE role_name='TEACHER'),:dept,1)",{'id':uid(),'name':r[0],'email':r[1],'pw':r[2],'dept':r[3]})
        cur.execute("UPDATE teacher_signup_requests SET status=:status,password_hash='!',resolved_at=CURRENT_TIMESTAMP,resolved_by=:admin WHERE request_id=:id",{'status':'APPROVED' if approve else 'REJECTED','admin':user['user_id'],'id':request_id})
        audit_event(cur,user,'TEACHER_SIGNUP_APPROVED' if approve else 'TEACHER_SIGNUP_REJECTED',request_id)

def request_attendance_correction(user,attendance_id,status,reason):
    require_actor(user,('STUDENT',))
    if status not in ('PRESENT','ABSENT','LATE'):raise ValueError('Invalid correction request.')
    if not reason.strip() or len(reason.strip())>500:raise ValueError('Enter a reason of up to 500 characters.')
    with connection() as c:
        cur=c.cursor();_active_actor(cur,user,('STUDENT',));cur.execute('SELECT status FROM attendance WHERE attendance_id=:id AND student_id=:student FOR UPDATE WAIT 5',{'id':attendance_id,'student':user['user_id']});record=cur.fetchone()
        if not record:raise ValueError('Attendance record not found.')
        if record[0]==status:raise ValueError('Choose a status different from the current status.')
        cur.execute("SELECT COUNT(*) FROM attendance_correction_requests WHERE attendance_id=:id AND status='PENDING'",{'id':attendance_id})
        if cur.fetchone()[0]:raise ValueError('A request for this record is already pending.')
        cur.execute("INSERT INTO attendance_correction_requests(request_id,attendance_id,student_id,requested_status,reason) VALUES(:id,:attendance,:student,:status,:reason)",{'id':uid(),'attendance':attendance_id,'student':user['user_id'],'status':status,'reason':reason.strip()})
        audit_event(cur,user,'ATTENDANCE_CORRECTION_REQUESTED',attendance_id,'requested_status='+status)

def correction_requests(user):
    require_actor(user,('STUDENT','TEACHER'))
    if user['role']=='STUDENT':
        return rows("SELECT r.request_id,c.course_code,a.session_date,r.requested_status,r.reason,r.status,r.created_at FROM attendance_correction_requests r JOIN attendance a ON a.attendance_id=r.attendance_id JOIN courses c ON c.course_id=a.course_id WHERE r.student_id=:id ORDER BY r.created_at DESC",{'id':user['user_id']})
    if user['role']=='TEACHER':
        return rows("SELECT r.request_id,c.course_code,s.roll_number,s.full_name,a.session_date,a.status current_status,r.requested_status,r.reason,r.status FROM attendance_correction_requests r JOIN attendance a ON a.attendance_id=r.attendance_id JOIN courses c ON c.course_id=a.course_id JOIN students s ON s.student_id=r.student_id WHERE c.teacher_id=:id AND r.status='PENDING' ORDER BY r.created_at",{'id':user['user_id']})
    raise ValueError('Invalid role.')

def resolve_attendance_request(user,request_id,approve):
    require_actor(user,('TEACHER',))
    with connection() as c:
        cur=c.cursor();_active_actor(cur,user,('TEACHER',));policy=_attendance_policy(cur)
        cur.execute("SELECT r.attendance_id,r.requested_status,r.reason,a.status,a.session_date FROM attendance_correction_requests r JOIN attendance a ON a.attendance_id=r.attendance_id JOIN courses c ON c.course_id=a.course_id WHERE r.request_id=:id AND r.status='PENDING' AND c.teacher_id=:teacher AND c.is_active=1 FOR UPDATE OF r.status,a.status WAIT 5",{'id':request_id,'teacher':user['user_id']});r=cur.fetchone()
        if not r:raise ValueError('Request not found or no longer pending.')
        if approve:
            _check_edit_window(r[4],policy)
            cur.execute('UPDATE attendance SET status=:status,remarks=:reason WHERE attendance_id=:id',{'status':r[1],'reason':r[2],'id':r[0]})
        cur.execute("UPDATE attendance_correction_requests SET status=:status,resolved_by=:teacher,resolved_at=CURRENT_TIMESTAMP WHERE request_id=:id",{'status':'APPROVED' if approve else 'REJECTED','teacher':user['user_id'],'id':request_id})
        audit_event(cur,user,'ATTENDANCE_REQUEST_APPROVED' if approve else 'ATTENDANCE_REQUEST_REJECTED',r[0],f'old_status={r[3]}; requested_status={r[1]}; request={request_id}')


def students_for_roll(roll):
    if not roll.strip():return []
    return rows("SELECT student_id,roll_number,full_name,is_active FROM students WHERE UPPER(roll_number)=:roll ORDER BY is_active DESC",{'roll':roll.strip().upper()})

def teacher_for_email(email):
    if not email.strip():return None
    return one("SELECT u.user_id,u.full_name,u.email,u.is_active,r.role_name FROM users u JOIN roles r ON r.role_id=u.role_id WHERE LOWER(u.email)=:email",{'email':email.strip().lower()})

def course_for_code(code):
    if not code.strip():return None
    return one("SELECT c.course_id,c.course_code,c.course_name,c.is_active,u.is_active teacher_active FROM courses c JOIN users u ON u.user_id=c.teacher_id WHERE UPPER(c.course_code)=:code",{'code':code.strip().upper()})

def delete_course_permanently(course_id,*,actor=None):
    with connection() as c:
        cur=c.cursor();_admin_action(cur,actor);cur.execute('DELETE FROM courses WHERE course_id=:id',{'id':course_id})
        if cur.rowcount!=1:raise ValueError('Course not found.')
        _admin_audit(cur,actor,'COURSE_DELETED',course_id)

def delete_teacher_permanently(teacher_id,*,actor=None):
    with connection() as c:
        cur=c.cursor();_admin_action(cur,actor);cur.execute("SELECT u.email FROM users u JOIN roles r ON r.role_id=u.role_id WHERE u.user_id=:id AND r.role_name='TEACHER' FOR UPDATE OF u.is_active WAIT 5",{'id':teacher_id});row=cur.fetchone()
        if not row:raise ValueError('Teacher not found.')
        # Deleting assigned courses cascades enrollment, attendance and QR sessions.
        cur.execute('DELETE FROM courses WHERE teacher_id=:id',{'id':teacher_id})
        cur.execute('DELETE FROM attendance WHERE teacher_id=:id',{'id':teacher_id})
        cur.execute('DELETE FROM checkin_sessions WHERE teacher_id=:id',{'id':teacher_id})
        cur.execute("DELETE FROM password_reset_requests WHERE user_type='TEACHER' AND user_id=:id",{'id':teacher_id})
        cur.execute('DELETE FROM teacher_signup_requests WHERE LOWER(email)=LOWER(:email)',{'email':row[0]})
        cur.execute('DELETE FROM users WHERE user_id=:id',{'id':teacher_id})
        _admin_audit(cur,actor,'TEACHER_DELETED',teacher_id)

def student_profile(user):
    require_actor(user,('STUDENT',))
    return one('''SELECT s.student_id,s.roll_number,s.full_name,l.email,s.phone,s.semester,s.batch_year,s.face_enrolled,d.dept_name
        FROM students s JOIN student_logins l ON l.student_id=s.student_id JOIN departments d ON d.dept_id=s.dept_id
        WHERE s.student_id=:id AND s.is_active=1 AND l.is_active=1''',{'id':user['user_id']})

def admin_dashboard_stats(user):
    require_actor(user,('ADMIN',))
    return one('''SELECT (SELECT COUNT(*) FROM students WHERE is_active=1) student_count,
        (SELECT COUNT(*) FROM users u JOIN roles r ON r.role_id=u.role_id WHERE u.is_active=1 AND r.role_name='TEACHER') teacher_count,
        (SELECT COUNT(*) FROM courses WHERE is_active=1) course_count,
        (SELECT COUNT(*) FROM attendance) record_count,
        (SELECT COUNT(*) FROM (SELECT DISTINCT course_id,session_date FROM attendance)) session_count FROM dual''')

def audit_records(user,limit=200):
    require_actor(user,('ADMIN',))
    if type(limit) is not int or not 1<=limit<=1000:raise ValueError('Audit record limit must be between 1 and 1000.')
    if not session_is_active(user):raise ValueError('Your administrator account is no longer active.')
    return rows('''SELECT event_id,actor_id,actor_role,action,entity_id,detail,created_at
        FROM app_audit ORDER BY created_at DESC,event_id FETCH FIRST :row_limit ROWS ONLY''',{'row_limit':limit})

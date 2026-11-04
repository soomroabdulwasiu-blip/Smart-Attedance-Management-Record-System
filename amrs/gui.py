from pathlib import Path
from datetime import date,datetime
import sys,os,time,cv2
from PySide6.QtCore import Qt, QTimer, QSignalBlocker, QPropertyAnimation, QEasingCurve, QObject, Signal, QRunnable, QThreadPool, QEvent
from PySide6.QtGui import QImage,QPixmap,QColor,QPainter
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,
 QPushButton,QComboBox,QSpinBox,QTabWidget,QTableWidget,QTableWidgetItem,QMessageBox,QFileDialog,QDateEdit,QDialog,QInputDialog,
 QFrame,QStackedWidget,QScrollArea,QSizePolicy,QGraphicsDropShadowEffect,QGraphicsOpacityEffect,QGridLayout,QHeaderView,QListWidget,QCheckBox)
from PySide6.QtCore import QDate
from . import db
from . import settings
from .face import FaceEngine,CameraWorker,CameraProbeWorker,BatchEnrollmentWorker,CaptureEnrollmentWorker,preview_frame

STYLE="""
QWidget { font-family: 'Segoe UI'; font-size: 13px; color: #24344c; }
QMainWindow, QWidget#appRoot { background: #f4f6fb; }
QPushButton { background: #2e75b6; color: white; padding: 10px 16px; border: 0; border-radius: 6px; font-weight: 600; }
QPushButton:hover { background: #245f98; }
QPushButton:pressed { background: #1b4a7b; }
QLineEdit, QComboBox, QSpinBox, QDateEdit { background: white; color: #1c2e46; border: 1px solid #ccd7e5; border-radius: 6px; padding: 8px 10px; min-height: 18px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus { border: 1px solid #2e75b6; }
QTableWidget { background: white; alternate-background-color: #f8faff; border: 1px solid #e1e8f2; border-radius: 6px; gridline-color: #eef2f8; selection-background-color: #dceaf9; selection-color: #163c69; }
QHeaderView::section { background: #eaf0f8; color: #29486c; border: none; border-bottom: 1px solid #dce5f0; padding: 10px; font-weight: 600; }
QTableCornerButton::section { background: #eaf0f8; border: none; }
QListWidget { background:white; border:1px solid #e1e8f2; border-radius:6px; padding:6px; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QWidget#loginRoot { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0f1b35,stop:0.55 #1b3a6b,stop:1 #2e75b6); }
QLabel#loginLogo { color: white; font-size: 34px; font-weight: 750; background: transparent; }
QLabel#loginIcon { color: white; font-size: 38px; background: transparent; }
QLabel#loginTagline { color: #a7c3df; font-size: 12px; background: transparent; }
QFrame#loginCard { background: white; border-radius: 14px; }
QWidget#loginHeader { background: #1b3a6b; border-top-left-radius: 13px; border-top-right-radius: 13px; }
QLabel#loginHeaderTitle { color: white; font-size: 17px; font-weight: 700; background: transparent; }
QLabel#loginHeaderSub { color: #a7c3df; font-size: 11px; background: transparent; }
QWidget#loginContent { background: white; }
QWidget#loginFooter { background: #f4f6fb; border-bottom-left-radius: 13px; border-bottom-right-radius: 13px; }
QLabel#footerText { color: #899cb0; font-size: 11px; background: transparent; }
QPushButton#roleAdmin { background: #2e75b6; min-height: 30px; text-align: left; padding-left: 24px; }
QPushButton#roleTeacher { background: #27ae60; min-height: 30px; text-align: left; padding-left: 24px; }
QPushButton#roleStudent { background: #e8a020; min-height: 30px; text-align: left; padding-left: 24px; }
QPushButton#roleAdmin:hover { background: #245f98; } QPushButton#roleTeacher:hover { background: #218c50; } QPushButton#roleStudent:hover { background: #c98513; }
QPushButton#linkButton { background: transparent; color: #2e75b6; padding: 4px; font-weight: 500; }
QPushButton#linkButton:hover { color: #174c83; text-decoration: underline; }
QWidget#sidebar { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #101f3b,stop:1 #132849); }
QWidget#sidebarBrand { background: #091225; }
QLabel#sideLogo { color: white; font-size: 20px; font-weight: 750; background: transparent; }
QLabel#sideWelcome { color: #8bafd4; font-size: 12px; background: transparent; }
QLabel#roleBadge { color: white; background: #e8a020; border-radius: 10px; padding: 4px 12px; font-size: 10px; font-weight: 700; }
QPushButton#navButton { background: transparent; color: #a8bfd8; padding: 11px 15px; text-align: left; border-radius: 7px; }
QPushButton#navButton:hover, QPushButton#navButton:checked { background: #1b3a6b; color: white; }
QPushButton#logoutButton { background: transparent; color: #e98d8d; text-align: left; padding: 11px 15px; }
QPushButton#logoutButton:hover { background: #3a1515; }
QWidget#contentPage { background: #f4f6fb; }
QLabel#pageTitle { color: #172b49; font-size: 26px; font-weight: 700; }
QLabel#sectionSubtitle { color: #73869d; font-size: 13px; }
QFrame#statCard { background: white; border: 1px solid #e1e9f4; border-radius: 12px; }
QFrame#statCard:hover { border: 1px solid #b7d1eb; }
QLabel#statLabel { color: #7e90a7; font-size: 12px; }
QLabel#statValue { color: #1b3a6b; font-size: 28px; font-weight: 700; }
QLabel#statIcon { color: #2e75b6; font-size: 19px; background: #eaf3fc; border-radius: 16px; }
QDialog { background: #f4f6fb; }
QFrame#sectionCard { background: white; border: 1px solid #e0e8f2; border-radius: 10px; }
QLabel#sectionTitle { color: #1b3558; font-size: 16px; font-weight: 700; background: transparent; }
QLabel#fieldLabel { color: #455d78; font-size: 12px; font-weight: 600; background: transparent; }
QLabel#helperText { color: #71869f; font-size: 12px; background: transparent; }
QPushButton#secondaryButton { background: #edf3fa; color: #285780; border: 1px solid #d5e2ef; }
QPushButton#secondaryButton:hover { background: #dbeaf8; }
QPushButton#dangerButton { background: #fff2f1; color: #b54848; border: 1px solid #f3d7d5; }
QPushButton#dangerButton:hover { background: #fce3e0; }
QPushButton#successButton { background: #219b5a; color: white; }
QPushButton#successButton:hover { background: #1b814a; }
QLabel#dialogTitle { color:#1b3558; font-size:22px; font-weight:700; }
QLabel#dialogSubtitle { color:#71869f; font-size:12px; }
QWidget#workspaceHeader { background: white; border-bottom: 1px solid #e2e9f2; }
QLabel#workspaceTitle { color:#193454; font-size:14px; font-weight:700; background:transparent; }
QLabel#workspaceMeta { color:#7a8fa8; font-size:11px; background:transparent; }
QLabel#workspaceBadge { color:#2a669d; background:#eaf3fc; padding:5px 10px; border-radius:10px; font-size:10px; font-weight:700; }
QCheckBox { spacing:8px; color:#3f5975; background:transparent; }

"""
def alert(parent,text,title='AMRS') : QMessageBox.information(parent,title,str(text))
def error(parent,e):
    try:
        from .diagnostics import record
        record('UI_OPERATION_FAILED',e)
    except OSError:pass
    detail=e.args[0] if isinstance(e,Exception) and e.args else None
    code=getattr(detail,'code',None)
    if code==1:message='A record with these details already exists. Check the roll number, email or course code.'
    elif code in (2291,2292):message='This action conflicts with related records. Check the selected student, course or teacher.'
    elif code in (1017,12154,12514,12541,12545):message='Cannot connect to Oracle. Check the database service and connection settings.'
    elif isinstance(e,Exception) and type(e).__module__.startswith('oracledb'):message=f'Oracle operation failed (code {code}). Check permissions, connectivity and the selected records.'
    else:message=str(e)
    QMessageBox.warning(parent,'AMRS',message)
def safe(fn):
    def run(*args):
        try: return fn(*args)
        except Exception as e: error(args[0] if args else None,e)
    return run
def field(placeholder='',password=False):
    w=QLineEdit();w.setPlaceholderText(placeholder)
    if password:w.setEchoMode(QLineEdit.EchoMode.Password)
    return w
def button(text,fn):
    b=QPushButton(text);b.clicked.connect(fn);return b

# Shared visual language for the three role workspaces.
STYLE += """
QWidget { font-family: 'Segoe UI'; color: #233453; }
QMainWindow, QWidget#appRoot, QWidget#contentPage { background: #f3f6fc; }
QWidget#sidebar { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #101a36,stop:1 #182c52); }
QWidget#sidebarBrand { background: #101a36; }
QWidget#workspaceHeader { background: #ffffff; border-bottom: 1px solid #e6ecf5; }
QLabel#pageTitle { color: #172746; font-size: 28px; font-weight: 700; }
QLabel#sectionSubtitle, QLabel#helperText { color: #667c99; }
QFrame#sectionCard, QFrame#statCard { background: #ffffff; border: 1px solid #e3eaf5; border-radius: 14px; }
QLabel#statIcon { color: #3d5de1; background: #eef1ff; border-radius: 14px; }
QLabel#statValue { color: #182d55; font-size: 30px; font-weight: 700; }
QPushButton { background: #425bd7; color: #ffffff; border-radius: 8px; padding: 10px 16px; font-weight: 600; }
QPushButton:hover { background: #3449b8; }
QPushButton#navButton { color: #afc1df; border-radius: 8px; padding: 11px 15px; background: transparent; }
QPushButton#navButton:hover, QPushButton#navButton:checked { background: #2d416a; color: white; }
QLineEdit, QComboBox, QSpinBox, QDateEdit { background: white; border: 1px solid #d7e0ef; border-radius: 8px; padding: 8px 10px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus { border: 1px solid #6c7de7; }
QHeaderView::section { background: #f4f7fc; color: #506784; border: none; border-bottom: 1px solid #e1e8f2; padding: 11px; font-weight: 600; }
QTableWidget, QListWidget { background: white; border: 1px solid #e2eaf5; border-radius: 9px; }
QFrame#dashboardHero { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #233876,stop:1 #405bd2); border: none; border-radius: 16px; }
QLabel#heroTitle { color: white; font-size: 22px; font-weight: 700; background: transparent; }
QLabel#heroText { color: #dbe5ff; font-size: 13px; background: transparent; }
QLabel#attendanceSuccess { background: #e9f9f1; color: #087446; border: 1px solid #a7e3c6; border-radius: 10px; padding: 13px; font-size: 15px; font-weight: 700; }
"""

# Dark workspace theme applies to all role pages while keeping login dialogs legible.
STYLE += """
QMainWindow, QWidget#appRoot, QWidget#contentPage { background: #0b1020; }
QWidget#sidebar { background: #101827; border-right: 1px solid #27354d; }
QWidget#sidebarBrand { background: #101827; }
QLabel#sideLogo { color: #f4f7ff; font-size: 21px; font-weight: 750; }
QLabel#sideWelcome { color: #9eafc9; }
QPushButton#navButton { background: transparent; color: #a8b8d1; border: 0; border-radius: 9px; padding: 11px 14px; }
QPushButton#navButton:hover { background: #202e46; color: #f4f7ff; }
QPushButton#navButton:checked { background: #384c86; color: #ffffff; }
QPushButton#logoutButton { color: #f5a9b3; }
QPushButton#logoutButton:hover { background: #432536; }
QWidget#workspaceHeader { background: #111a2c; border-bottom: 1px solid #293750; }
QLabel#workspaceTitle { color: #f2f6ff; font-size: 15px; font-weight: 700; }
QLabel#workspaceMeta { color: #96aac9; }
QLabel#workspaceBadge { background: #263759; color: #bacbff; border-radius: 10px; padding: 6px 12px; }
QLabel#pageTitle { color: #f5f7ff; font-size: 27px; font-weight: 700; }
QLabel#sectionSubtitle, QLabel#helperText { color: #a9b9d1; }
QFrame#sectionCard, QFrame#statCard { background: #162238; border: 1px solid #2d3d58; border-radius: 14px; }
QFrame#statCard:hover { border: 1px solid #607ac8; }
QLabel#sectionTitle { color: #f2f6ff; font-size: 16px; font-weight: 700; background: transparent; }
QLabel#fieldLabel { color: #c1cee2; font-size: 12px; font-weight: 600; background: transparent; }
QLabel#statLabel { color: #adc0dd; }
QLabel#statValue { color: #ffffff; }
QLabel#statIcon { color: #dbe4ff; background: #314578; border-radius: 14px; }
QFrame#dashboardHero { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #393b91,stop:0.55 #3554a6,stop:1 #287b8e); border: 1px solid #5977bd; border-radius: 16px; }
QWidget#contentPage { color: #d8e3f5; }
QWidget#contentPage QLineEdit, QWidget#contentPage QComboBox, QWidget#contentPage QSpinBox, QWidget#contentPage QDateEdit { color: #eff5ff; background: #101b2e; border: 1px solid #405273; border-radius: 8px; padding: 8px 10px; min-height: 20px; selection-background-color: #526fbc; }
QWidget#contentPage QLineEdit:focus, QWidget#contentPage QComboBox:focus, QWidget#contentPage QSpinBox:focus, QWidget#contentPage QDateEdit:focus { border: 1px solid #8da9ff; }
QWidget#contentPage QLineEdit:disabled, QWidget#contentPage QComboBox:disabled, QWidget#contentPage QDateEdit:disabled { color: #8595af; background: #1b273a; }
QWidget#contentPage QComboBox QAbstractItemView { background: #1a2940; color: #edf3ff; border: 1px solid #405273; selection-background-color: #435d9f; }
QWidget#contentPage QTableWidget, QWidget#contentPage QListWidget { color: #e5edfa; background: #111c2e; alternate-background-color: #17243a; border: 1px solid #34445e; border-radius: 9px; gridline-color: #273851; selection-background-color: #3b5689; selection-color: #ffffff; }
QWidget#contentPage QTableWidget::item { padding: 6px; }
QWidget#contentPage QHeaderView::section { background: #243650; color: #c6d4ea; border: 0; border-bottom: 1px solid #40516c; padding: 10px; font-weight: 600; }
QWidget#contentPage QTableCornerButton::section { background: #243650; border: 0; }
QWidget#contentPage QPushButton#secondaryButton { color: #d7e5ff; background: #273b5b; border: 1px solid #415a80; }
QWidget#contentPage QPushButton#secondaryButton:hover { background: #37547b; }
QWidget#contentPage QPushButton#dangerButton { color: #ffc4cd; background: #482b3b; border: 1px solid #784457; }
QWidget#contentPage QPushButton#dangerButton:hover { background: #65384b; }
QWidget#contentPage QCheckBox { color: #d1ddf0; }
QWidget#contentPage QScrollBar:vertical { background: #111b2c; width: 10px; margin: 2px; }
QWidget#contentPage QScrollBar::handle:vertical { background: #506786; border-radius: 4px; min-height: 28px; }
QLabel#attendanceSuccess { background: #163d39; color: #b4f1d3; border: 1px solid #337e69; border-radius: 10px; padding: 13px; font-size: 15px; font-weight: 700; }
"""


def table(headers):
    t=QTableWidget(0,len(headers));t.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Expanding);t.setMinimumWidth(0);t.setHorizontalHeaderLabels(headers);t.horizontalHeader().setStretchLastSection(True)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);t.verticalHeader().setVisible(False);t.verticalHeader().setDefaultSectionSize(46)
    t.setAlternatingRowColors(True);t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);t.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);return t

def section(title,subtitle=None):
    box=QFrame();box.setObjectName('sectionCard');v=QVBoxLayout(box);v.setContentsMargins(20,18,20,20);v.setSpacing(12)
    label=QLabel(title);label.setObjectName('sectionTitle');v.addWidget(label)
    if subtitle:
        label=QLabel(subtitle);label.setWordWrap(True);label.setObjectName('helperText');v.addWidget(label)
    return box,v

def text_hint(value):
    w=QLabel(value);w.setObjectName('helperText');w.setWordWrap(True);return w

def form_cell(label,widget):
    box=QWidget();lay=QVBoxLayout(box);lay.setContentsMargins(0,0,0,0);lay.setSpacing(6)
    cap=QLabel(label);cap.setObjectName('fieldLabel');cap.setWordWrap(True);lay.addWidget(cap);lay.addWidget(widget);return box

def action(text,callback,kind='secondary'):
    b=button(text,callback);b.setObjectName({'secondary':'secondaryButton','danger':'dangerButton','success':'successButton'}.get(kind,''));return b

def dialog_shell(dialog,title,subtitle,width=720):
    dialog.setWindowTitle(title);dialog.setMinimumWidth(width);outer=QVBoxLayout(dialog);outer.setContentsMargins(24,24,24,24);outer.setSpacing(12)
    heading=QLabel(title);heading.setObjectName('dialogTitle');outer.addWidget(heading)
    if subtitle:label=QLabel(subtitle);label.setObjectName('dialogSubtitle');label.setWordWrap(True);outer.addWidget(label)
    box,body=section('Details');outer.addWidget(box);return outer,body

def fill(t,records,cols):
    t.setRowCount(len(records))
    palette={'PRESENT':('#167749','#e7f6ed'),'ABSENT':('#b13f42','#fff0ef'),'LATE':('#a66312','#fff5e3'),
             'ENROLLED':('#167749','#e7f6ed'),'NOT ENROLLED':('#73869d','#f3f6fa')}
    for r,row in enumerate(records):
        for c,key in enumerate(cols):
            value=row.get(key);item=QTableWidgetItem(str(value if value is not None else ''))
            if key in ('status','face_status') and str(value).upper() in palette:
                fg,bg=palette[str(value).upper()];item.setForeground(QColor(fg));item.setBackground(QColor(bg));item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            t.setItem(r,c,item)
def load_combo(combo,items,label,id_key):
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);combo.setMinimumContentsLength(8);combo.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
    combo.clear()
    for row in items:combo.addItem(label(row),row[id_key])

def course_label(row):return row['course_code']+' — '+row['course_name']
def student_label(row):return row['roll_number']+' — '+row['full_name']

class TaskSignals(QObject):
    succeeded=Signal(object)
    failed=Signal(object)

class BackgroundTask(QRunnable):
    def __init__(self,fn):
        super().__init__();self.fn=fn;self.signals=TaskSignals()
    def run(self):
        try:self.signals.succeeded.emit(self.fn())
        except Exception as exc:self.signals.failed.emit(exc)

class CameraPreview(QWidget):
    """Scale each camera frame to the available viewport without cropping faces."""
    def __init__(self,parent=None):
        super().__init__(parent);self.image=None;self.setMinimumSize(320,360)
        self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Expanding)
    def setImage(self,image):
        self.image=image;self.update()
    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor('#0a1220'))
        if self.image is None:
            painter.setPen(QColor('#b7c8e0'));painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'Camera preview\nChoose a course and start attendance')
            return
        image_size=self.image.size();image_size.scale(self.size(),Qt.AspectRatioMode.KeepAspectRatio)
        x=(self.width()-image_size.width())//2;y=(self.height()-image_size.height())//2
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        from PySide6.QtCore import QRect
        painter.drawImage(QRect(x,y,image_size.width(),image_size.height()),self.image)

class Signup(QDialog):
    def __init__(self,parent,role):
        super().__init__(parent);self.role=role
        outer,body=dialog_shell(self,role.title()+' Sign Up','Create your account to access the attendance system.')
        self.name=field('Enter full name');self.email=field('Your email is your username');self.password=field('Minimum 8 characters',password=True);self.confirm=field('Re-enter your password',password=True)
        self.dept=QComboBox();self._signup_task=None
        if parent is None:load_combo(self.dept,db.departments(),lambda r:r['dept_name'],'dept_id')
        grid=QGridLayout();grid.setHorizontalSpacing(16);grid.setVerticalSpacing(14)
        for i,(label,w) in enumerate([('Full name *',self.name),('Email / username *',self.email),('Password *',self.password),('Confirm password *',self.confirm),('Department',self.dept)]):grid.addWidget(form_cell(label,w),i//2,i%2)
        if role=='STUDENT':
            self.roll=field('e.g. 2024-SE-001');self.sem=QSpinBox();self.sem.setRange(1,8);self.year=QSpinBox();self.year.setRange(1990,date.today().year+1);self.year.setValue(date.today().year)
            for i,(label,w) in enumerate([('Roll number *',self.roll),('Semester',self.sem),('Batch year',self.year)],start=5):grid.addWidget(form_cell(label,w),i//2,i%2)
            body.addWidget(text_hint('Already have a student record? Ask your administrator to create your login.'))
        body.addLayout(grid);self.signup_status=text_hint('');outer.addWidget(self.signup_status);footer=QHBoxLayout();footer.addStretch();footer.addWidget(action('Cancel',self.reject));self.create_button=button('Create account',self.submit);footer.addWidget(self.create_button);outer.addLayout(footer)
        if parent is not None:
            self.create_button.setEnabled(False);self.signup_status.setText('Loading departments…');task=BackgroundTask(db.departments);self._signup_task=task
            def loaded(rows):self._signup_task=None;load_combo(self.dept,rows,lambda r:r['dept_name'],'dept_id');self.create_button.setEnabled(bool(rows));self.signup_status.setText('')
            def failed(exc):self._signup_task=None;self.signup_status.setText('Cannot load departments. Check Oracle connection and try again.');error(self,exc)
            task.signals.succeeded.connect(loaded,Qt.ConnectionType.QueuedConnection);task.signals.failed.connect(failed,Qt.ConnectionType.QueuedConnection);QThreadPool.globalInstance().start(task)
    @safe
    def submit(self):
        if self._signup_task is not None:return
        if self.password.text()!=self.confirm.text():raise ValueError('Passwords do not match.')
        if self.role=='TEACHER':
            args=(self.name.text(),self.email.text(),self.password.text(),self.dept.currentText());operation=lambda:db.request_teacher_signup(*args)
        else:
            args=(self.name.text(),self.email.text(),self.password.text(),self.roll.text(),self.dept.currentData(),self.sem.value(),self.year.value());operation=lambda:db.signup_student(*args)
        def done(_):self._signup_task=None;self.password.clear();self.confirm.clear();alert(self,'Request submitted. An administrator must approve it before you can log in.' if self.role=='TEACHER' else 'Account created. You can log in now.');self.accept()
        if self.parent() is None:done(operation());return
        self.create_button.setEnabled(False);self.signup_status.setText('Creating account…');task=BackgroundTask(operation);self._signup_task=task
        def failed(exc):self._signup_task=None;self.create_button.setEnabled(True);self.signup_status.setText('Account was not created. Review the error and try again.');error(self,exc)
        task.signals.succeeded.connect(done,Qt.ConnectionType.QueuedConnection);task.signals.failed.connect(failed,Qt.ConnectionType.QueuedConnection);QThreadPool.globalInstance().start(task)
    def done(self,result):
        if self._signup_task is not None:self.signup_status.setText('Wait for the current operation to finish.');return
        super().done(result)

class Login(QWidget):
    def __init__(self):
        super().__init__();self.setObjectName('loginRoot');self.setWindowTitle('AMRS — Attendance Management');self.setMinimumSize(680,650);self.resize(1000,760)
        v=QVBoxLayout(self);v.setContentsMargins(24,20,24,20);v.setSpacing(4);v.addStretch()
        icon=QLabel('🎓');icon.setObjectName('loginIcon');icon.setAlignment(Qt.AlignmentFlag.AlignCenter);v.addWidget(icon)
        brand=QLabel('AMRS');brand.setObjectName('loginLogo');brand.setAlignment(Qt.AlignmentFlag.AlignCenter);v.addWidget(brand)
        tagline=QLabel('Attendance Management Record System');tagline.setObjectName('loginTagline');tagline.setAlignment(Qt.AlignmentFlag.AlignCenter);v.addWidget(tagline)
        v.addSpacing(20);outer=QHBoxLayout();outer.addStretch();card=QFrame();card.setObjectName('loginCard');card.setFixedWidth(460)
        shadow=QGraphicsDropShadowEffect(card);shadow.setBlurRadius(26);shadow.setOffset(0,9);shadow.setColor(Qt.GlobalColor.darkGray);card.setGraphicsEffect(shadow)
        cv=QVBoxLayout(card);cv.setContentsMargins(0,0,0,0);cv.setSpacing(0)
        header=QWidget();header.setObjectName('loginHeader');hv=QVBoxLayout(header);hv.setContentsMargins(20,22,20,22);hv.setSpacing(5)
        self.header_title=QLabel('Welcome! Select Your Role');self.header_title.setObjectName('loginHeaderTitle');self.header_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header_sub=QLabel('Choose how you want to sign in');self.header_sub.setObjectName('loginHeaderSub');self.header_sub.setAlignment(Qt.AlignmentFlag.AlignCenter);hv.addWidget(self.header_title);hv.addWidget(self.header_sub);cv.addWidget(header)
        self.pages=QStackedWidget();self.pages.setObjectName('loginContent');roles=QWidget();roles.setObjectName('loginContent');rv=QVBoxLayout(roles);rv.setContentsMargins(36,28,36,28);rv.setSpacing(14)
        for role,label,style in [('ADMIN','🔐    Admin Login','roleAdmin'),('TEACHER','🧑‍🏫    Teacher Login','roleTeacher'),('STUDENT','🎓    Student Login','roleStudent')]:
            btn=button(label,lambda checked=False,r=role:self.select_role(r));btn.setObjectName(style);rv.addWidget(btn)
        self.pages.addWidget(roles);form=QWidget();form.setObjectName('loginContent');fv=QVBoxLayout(form);fv.setContentsMargins(36,22,36,20);fv.setSpacing(8)
        self.role=QComboBox();self.role.addItems(['ADMIN','TEACHER','STUDENT']);self.role.hide();self.identity=field();self.pw=field(password=True)
        self.identity_label=QLabel('Email / Username');fv.addWidget(self.identity_label);fv.addWidget(self.identity);fv.addSpacing(3);fv.addWidget(QLabel('Password'));fv.addWidget(self.pw);fv.addSpacing(8)
        self.signin_button=button('Sign In',self.login);fv.addWidget(self.signin_button);self.pw.returnPressed.connect(self.login);self._login_task=None
        self.signup_button=button('Create an account',lambda:self.signup(self.role.currentText()));self.signup_button.setObjectName('linkButton');fv.addWidget(self.signup_button)
        self.forgot_button=button('Forgot password?',self.forgot);self.forgot_button.setObjectName('linkButton');fv.addWidget(self.forgot_button)
        self.pages.addWidget(form);cv.addWidget(self.pages)
        footer=QWidget();footer.setObjectName('loginFooter');fh=QHBoxLayout(footer);fh.setContentsMargins(16,10,16,10);self.back=button('← Back',self.show_roles);self.back.setObjectName('linkButton');self.back.hide();fh.addWidget(self.back);fh.addStretch();foot=QLabel('AMRS  ·  Python');foot.setObjectName('footerText');fh.addWidget(foot);cv.addWidget(footer)
        outer.addWidget(card);outer.addStretch();v.addLayout(outer);v.addStretch()
    def select_role(self,role):
        self.identity.clear();self.pw.clear()
        self.identity.setPlaceholderText('Enter Student Email Address or Roll No' if role=='STUDENT' else f'Enter {role.title()} Email Address')
        self.pw.setPlaceholderText(f'Enter {role.title()} Password')
        self.identity_label.setText('Email / Roll number' if role=='STUDENT' else 'Email / Username');self.role.setCurrentText(role);self.header_title.setText(role.title()+' Login');self.header_sub.setText('Enter your credentials to continue');self.signup_button.setVisible(role!='ADMIN');self.forgot_button.setVisible(role!='ADMIN');self.back.show();self.pages.setCurrentIndex(1);self.identity.setFocus()
    def show_roles(self):
        self.header_title.setText('Welcome! Select Your Role');self.header_sub.setText('Choose how you want to sign in');self.pages.setCurrentIndex(0);self.back.hide();self.identity.clear();self.pw.clear()
    @safe
    def signup(self,role):Signup(self,role).exec()
    @safe
    def forgot(self):
        role=self.role.currentText()
        if role=='ADMIN':raise ValueError('Ask an administrator to reset this account.')
        from .recovery_ui import PasswordRecoveryDialog
        PasswordRecoveryDialog(self,role,self.identity.text()).exec()

    @safe
    def login(self):
        if self._login_task is not None:return
        role=self.role.currentText();identity=self.identity.text().strip();password=self.pw.text()
        if not identity or not password:raise ValueError('Enter your username and password.')
        self.pages.setEnabled(False);self.back.setEnabled(False);self.signin_button.setText('Signing in…')
        from .presentation_data import authenticate
        task=BackgroundTask(lambda:authenticate(role,identity,password));self._login_task=task
        task.signals.succeeded.connect(self._login_success,Qt.ConnectionType.QueuedConnection)
        task.signals.failed.connect(self._login_failure,Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(task)
    def _finish_login(self):
        self._login_task=None;self.pages.setEnabled(True);self.back.setEnabled(True);self.signin_button.setText('Sign In')
    def _login_success(self,user):
        try:
            self.main=MainWindow(user,self);self.main.show();self.hide();self.pw.clear()
        except Exception as exc:error(self,exc)
        finally:self._finish_login()
    def _login_failure(self,exc):
        self._finish_login();error(self,exc)

class MainWindow(QMainWindow):
    def __init__(self,user,login):
        super().__init__();self.user=user;self.login_window=login;self.worker=None;self.camera_probe=None;self.qrserver=None;self.setWindowTitle('AMRS — '+user['role']);self.resize(1280,800);self.setMinimumSize(950,650)
        body=QWidget();body.setObjectName('appRoot');self.setCentralWidget(body);shell=QHBoxLayout(body);shell.setContentsMargins(0,0,0,0);shell.setSpacing(0)
        side=QWidget();side.setObjectName('sidebar');side.setFixedWidth(220);sv=QVBoxLayout(side);sv.setContentsMargins(0,0,0,14);sv.setSpacing(0)
        brand=QWidget();brand.setObjectName('sidebarBrand');bv=QVBoxLayout(brand);bv.setContentsMargins(14,24,14,20);bv.setSpacing(6)
        logo=QLabel('🎓 AMRS');logo.setObjectName('sideLogo');logo.setAlignment(Qt.AlignmentFlag.AlignCenter);bv.addWidget(logo)
        self.side_welcome=QLabel(user['full_name']);self.side_welcome.setTextFormat(Qt.TextFormat.PlainText);self.side_welcome.setObjectName('sideWelcome');self.side_welcome.setWordWrap(True);self.side_welcome.setAlignment(Qt.AlignmentFlag.AlignCenter);bv.addWidget(self.side_welcome)
        badge=QLabel('ADMINISTRATOR' if user['role']=='ADMIN' else user['role']);badge.setObjectName('roleBadge');badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if user['role']=='TEACHER':badge.setStyleSheet('background:#27ae60;color:white;border-radius:10px;padding:4px 12px;font-weight:700;font-size:10px')
        if user['role']=='STUDENT':badge.setStyleSheet('background:#e8a020;color:white;border-radius:10px;padding:4px 12px;font-weight:700;font-size:10px')
        bv.addWidget(badge,0,Qt.AlignmentFlag.AlignCenter);sv.addWidget(brand)
        nav_area=QScrollArea();nav_area.setWidgetResizable(True);nav_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);nav_area.setStyleSheet('QScrollArea { background: transparent; border: none; }');nav_widget=QWidget();nav_widget.setObjectName('navigationContent');self.nav_layout=QVBoxLayout(nav_widget);self.nav_layout.setContentsMargins(8,10,8,0);self.nav_layout.setSpacing(2);self.nav_layout.addStretch();nav_area.setWidget(nav_widget);sv.addWidget(nav_area,1)
        out=button('🚪   Logout',self.logout);out.setObjectName('logoutButton');sv.addWidget(out);shell.addWidget(side)
        workspace=QWidget();workspace.setObjectName('appRoot');wv=QVBoxLayout(workspace);wv.setContentsMargins(0,0,0,0);wv.setSpacing(0)
        header=QWidget();header.setObjectName('workspaceHeader');header.setMinimumHeight(62);header_layout=QHBoxLayout(header);header_layout.setContentsMargins(32,10,32,10)
        header_text=QVBoxLayout();header_text.setSpacing(1);self.workspace_headline=QLabel('Dashboard');self.workspace_headline.setObjectName('workspaceTitle');header_text.addWidget(self.workspace_headline)
        caption=QLabel('Manage your classes, records and attendance');caption.setObjectName('workspaceMeta');header_text.addWidget(caption);header_layout.addLayout(header_text);header_layout.addStretch()
        today=QLabel(datetime.now().strftime('%d %b %Y'));today.setObjectName('workspaceMeta');header_layout.addWidget(today)
        role_label=QLabel(user['role']);role_label.setObjectName('workspaceBadge');header_layout.addWidget(role_label);wv.addWidget(header)
        self.tabs=QStackedWidget();self.tabs.setObjectName('contentStack');wv.addWidget(self.tabs,1);shell.addWidget(workspace,1);self.nav_buttons=[];self.page_titles=[];self._page_animation=None;self._animated_page=None
        snapshot=self.user.pop('_initial_reads',None)
        self._async_mode=snapshot is not None
        if snapshot is None:self.build_initial_pages()
        else:
            with db.use_reads(snapshot):self.build_initial_pages()
        self._action_tasks=set();self._session_check=None
        self._last_activity=time.monotonic();QApplication.instance().installEventFilter(self)
        self.session_timer=QTimer(self);self.session_timer.setInterval(60000);self.session_timer.timeout.connect(self.check_session);self.session_timer.start()
    def build_initial_pages(self):
        user=self.user
        self.setup_dashboard()
        if user['role']=='ADMIN':self.setup_admin()
        if user['role']=='TEACHER':self.setup_teacher()
        if user['role'] in ('TEACHER','STUDENT'):
            from .operations_ui import MyClassesPanel
            v=self.add_tab('My classes & profile');self.my_classes_panel=MyClassesPanel(user,self);v.addWidget(self.my_classes_panel)
        self.setup_history();
        if user['role'] in ('TEACHER','STUDENT'):self.setup_correction_requests()
        if user['role'] in ('ADMIN','TEACHER'):self.setup_reports()
        self.setup_account();self.select_tab(0)
    def check_session(self):
        if time.monotonic()-self._last_activity>=1800:self.logout();return
        if self._session_check is not None:return
        task=BackgroundTask(lambda:db.session_is_active(self.user));self._session_check=task
        def done(active):
            self._session_check=None
            if not active:self.logout()
        def failed(exc):self._session_check=None
        task.signals.succeeded.connect(done,Qt.ConnectionType.QueuedConnection);task.signals.failed.connect(failed,Qt.ConnectionType.QueuedConnection);QThreadPool.globalInstance().start(task)
    def eventFilter(self,target,event):
        if event.type() in (QEvent.Type.KeyPress,QEvent.Type.MouseButtonPress,QEvent.Type.Wheel) and isinstance(target,QWidget) and (target is self or self.isAncestorOf(target)):self._last_activity=time.monotonic()
        return super().eventFilter(target,event)
    def submit_action(self,fn,done=None,message='Saved successfully.'):
        if not self._async_mode:
            result=fn()
            if done:done(result)
            return
        task=BackgroundTask(fn);self._action_tasks.add(task);self.statusBar().showMessage('Working…')
        def success(result):
            self._action_tasks.discard(task);self.statusBar().showMessage(message,8000)
            try:
                if done:done(result)
            except Exception as exc:error(self,exc)
        def failure(exc):self._action_tasks.discard(task);self.statusBar().showMessage('Operation failed.',8000);error(self,exc)
        task.signals.succeeded.connect(success,Qt.ConnectionType.QueuedConnection);task.signals.failed.connect(failure,Qt.ConnectionType.QueuedConnection);QThreadPool.globalInstance().start(task)
    def logout(self):self.close()
    def closeEvent(self,event):
        if getattr(self,'_action_tasks',None):
            self.statusBar().showMessage('Finishing the current operation before sign out…');event.ignore();QTimer.singleShot(250,self.close);return
        panels=[getattr(self,name,None) for name in ('hardware_panel','classes_panel','operations_panel','my_classes_panel')]
        if any(panel is not None and panel.tasks for panel in panels):
            self.statusBar().showMessage('Finishing background reads before sign out…');event.ignore();QTimer.singleShot(250,self.close);return
        if hasattr(self,'hardware_panel') and not self.hardware_panel.shutdown():
            self.statusBar().showMessage('Closing the camera safely…');event.ignore();QTimer.singleShot(250,self.close);return
        for worker in (self.worker,self.camera_probe):
            if worker and worker.isRunning():
                worker.running=False;worker.cancel_event.set();self.statusBar().showMessage('Stopping capture and completing pending attendance saves…');event.ignore();QTimer.singleShot(250,self.close);return
        if self.qrserver:
            self.stop_qr();event.ignore();QTimer.singleShot(250,self.close);return
        self.session_timer.stop();QApplication.instance().removeEventFilter(self);self.login_window.show_roles();self.login_window.show();event.accept()
    def select_tab(self,index):
        if not 0<=index<self.tabs.count():return
        if self._page_animation is not None:
            self._page_animation.stop();self._page_animation=None
            if self._animated_page is not None:self._animated_page.setGraphicsEffect(None)
        changed=self.tabs.currentIndex()!=index;self.tabs.setCurrentIndex(index);self.workspace_headline.setText(self.page_titles[index])
        for i,btn in enumerate(self.nav_buttons):btn.setChecked(i==index)
        if changed and os.getenv('AMRS_REDUCE_MOTION','0')!='1':
            page=self.tabs.currentWidget();effect=QGraphicsOpacityEffect(page);page.setGraphicsEffect(effect);effect.setOpacity(.72)
            anim=QPropertyAnimation(effect,b'opacity',self);anim.setDuration(220);anim.setStartValue(.72);anim.setEndValue(1.0);anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._page_animation=anim;self._animated_page=page
            def finished():
                if self._page_animation is anim:
                    page.setGraphicsEffect(None);self._page_animation=None;self._animated_page=None
            anim.finished.connect(finished);anim.start()
    def navigate_to(self,title):
        if title in self.page_titles:self.select_tab(self.page_titles.index(title))
    def add_tab(self,title):
        labels={'Dashboard':'⬛   Dashboard','Students & face enrollment':'👤   Students','Courses & enrollment':'📚   Courses','Teachers':'🧑‍🏫   Teachers','Password resets':'🔑   Password Resets','Mark attendance':'✅   Mark Attendance','Multi-face camera':'📷   Face Verify','QR attendance':'📱   QR Attendance','Attendance & reports':'📊   My Attendance' if self.user['role']=='STUDENT' else '📋   Attendance History','Course reports':'📊   Course Reports','Account':'🔑   Change Password'}
        sc=QScrollArea();sc.setWidgetResizable(True);sc.setFrameShape(QFrame.Shape.NoFrame);sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded);page=QWidget();page.setObjectName('contentPage');v=QVBoxLayout(page);v.setContentsMargins(32,30,32,30);v.setSpacing(14)
        heading=QLabel({'Students & face enrollment':'Student Management','Courses & enrollment':'Course Management','Multi-face camera':'Face Attendance','Attendance & reports':'Attendance History'}.get(title,title));heading.setObjectName('pageTitle');heading.setWordWrap(True);v.addWidget(heading);sc.setWidget(page);index=self.tabs.addWidget(sc);self.page_titles.append(title)
        if title=='Account' and self.user['role']=='ADMIN':labels[title]='🔑   Account'
        nav=button(labels.get(title,title),lambda checked=False,i=index:self.select_tab(i));nav.setObjectName('navButton');nav.setCheckable(True);self.nav_buttons.append(nav);self.nav_layout.insertWidget(self.nav_layout.count()-1,nav)
        return v
    def setup_dashboard(self):
        v=self.add_tab('Dashboard')
        hero=QFrame();hero.setObjectName('dashboardHero');hero_layout=QVBoxLayout(hero);hero_layout.setContentsMargins(24,20,24,20);hero_layout.setSpacing(5)
        self.dashboard_greeting=QLabel('Welcome back, '+self.user['full_name']);self.dashboard_greeting.setTextFormat(Qt.TextFormat.PlainText);self.dashboard_greeting.setObjectName('heroTitle');self.dashboard_greeting.setWordWrap(True);hero_layout.addWidget(self.dashboard_greeting)
        subtitle=QLabel({'ADMIN':'Manage people, courses and approvals from one place.','TEACHER':'Your courses, attendance and student requests at a glance.','STUDENT':'Follow your courses and keep track of your attendance.'}[self.user['role']]);subtitle.setObjectName('heroText');subtitle.setWordWrap(True);hero_layout.addWidget(subtitle);v.addWidget(hero)
        self.dashboard_values=[];cards=QHBoxLayout();cards.setSpacing(14)
        if self.user['role']=='ADMIN':labels=[('👤','Active students'),('📚','Active courses'),('📋','Attendance records')]
        elif self.user['role']=='TEACHER':labels=[('📚','My courses'),('👥','Enrolled students'),('📋','Attendance records')]
        else:labels=[('📚','My courses'),('📊','Overall attendance'),('✅','Total present')]
        for icon,label in labels:
            card=QFrame();card.setObjectName('statCard');card.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred);cv=QVBoxLayout(card);cv.setContentsMargins(20,18,20,18);cv.setSpacing(10)
            top=QHBoxLayout();caption=QLabel(label.upper());caption.setObjectName('statLabel');caption.setWordWrap(True);top.addWidget(caption,1)
            icon_label=QLabel(icon);icon_label.setObjectName('statIcon');icon_label.setFixedSize(42,42);icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter);top.addWidget(icon_label);cv.addLayout(top)
            value=QLabel('—');value.setObjectName('statValue');cv.addWidget(value);self.dashboard_values.append(value);cards.addWidget(card,1)
        v.addLayout(cards)
        box,body=section('Quick actions','Open the tools you use most often.')
        actions=QGridLayout();actions.setHorizontalSpacing(10);actions.setVerticalSpacing(10)
        if self.user['role']=='ADMIN':choices=[('👤  Manage students','Students & face enrollment'),('📚  Manage courses','Courses & enrollment'),('🧑‍🏫  Manage teachers','Teachers'),('🔑  Reset requests','Password resets'),('✓  Teacher approvals','Teacher approvals')]
        elif self.user['role']=='TEACHER':choices=[('✅  Mark attendance','Mark attendance'),('📷  Face attendance','Multi-face camera'),('📱  QR attendance','QR attendance'),('📊  Course reports','Course reports'),('✉  Correction requests','Correction requests')]
        else:choices=[('📋  My attendance','Attendance & reports'),('✉  My requests','Correction requests'),('🔑  Change password','Account')]
        for i,(caption,target) in enumerate(choices):actions.addWidget(action(caption,lambda checked=False,t=target:self.navigate_to(t)),i//2,i%2)
        body.addLayout(actions);refresh=QHBoxLayout();refresh.addWidget(action('↻ Refresh overview',self.refresh_dashboard));refresh.addStretch();body.addLayout(refresh);v.addWidget(box)
        if self.user['role']=='STUDENT':
            box,body=section('Attendance summary by course','Attendance percentages follow the institution’s current settings.')
            self.dashboard_table=table(['Course','Subject','Present','Absent','Late','Attendance %']);self.dashboard_table.setMinimumHeight(180);body.addWidget(self.dashboard_table);v.addWidget(box)
        v.addStretch();self.refresh_dashboard()
    @safe
    def refresh_dashboard(self):
        if self.user['role']=='ADMIN':values=[len(db.students()),len(db.courses()),db.one('SELECT COUNT(*) n FROM attendance')['n']]
        elif self.user['role']=='TEACHER':
            stats=db.teacher_dashboard_stats(self.user['user_id']);values=[stats['course_count'],stats['student_count'],stats['record_count']]
        else:
            records=db.attendance(self.user);present=sum(1 for r in records if r['status']=='PRESENT');policy=db._attendance_policy();attended=sum(1 for r in records if r['status']=='PRESENT' or (r['status']=='LATE' and policy['late_counts_present']));pct=100*attended/len(records) if records else 0
            values=[len(db.courses(self.user)),f'{pct:.1f}%',present];self.refresh_student_summary()
        for label,value in zip(self.dashboard_values,values):label.setText(str(value))
    def refresh_student_summary(self):
        results=db.student_summary(self.user['user_id']);fill(self.dashboard_table,results,['course_code','course_name','present_count','absent_count','late_count','attendance_pct'])
    def setup_account(self):
        v=self.add_tab('Account')
        if self.user['role']=='ADMIN':
            profile,profile_body=section('Admin profile','Update your display name or login email. Enter your current password to change the email.')
            self.admin_name=field('Full name');self.admin_name.setMaxLength(200);self.admin_name.setText(self.user['full_name'])
            self.admin_email=field('Email used to sign in');self.admin_email.setMaxLength(254);self.admin_email.setText(self.user['email'])
            self.admin_profile_password=field('Required for email changes',password=True)
            profile_grid=QGridLayout();profile_grid.setHorizontalSpacing(16);profile_grid.setVerticalSpacing(14)
            profile_grid.addWidget(form_cell('Admin name',self.admin_name),0,0)
            profile_grid.addWidget(form_cell('Login email',self.admin_email),0,1)
            profile_grid.addWidget(form_cell('Current password',self.admin_profile_password),1,0)
            profile_body.addLayout(profile_grid)
            profile_body.addWidget(button('Save profile',self.save_admin_profile))
            v.addWidget(profile)
        box,body=section('Change password','Enter your current password, then choose a new password with at least 8 characters.')
        self.old_password=field('Current password',password=True);self.new_password=field('At least 8 characters',password=True);self.confirm_password=field('Repeat new password',password=True)
        grid=QGridLayout();grid.setHorizontalSpacing(16);grid.setVerticalSpacing(14)
        for i,(label,w) in enumerate([('Current password',self.old_password),('New password',self.new_password),('Confirm new password',self.confirm_password)]):grid.addWidget(form_cell(label,w),i//2,i%2)
        body.addLayout(grid);h=QHBoxLayout();h.addWidget(button('Save password',self.change_password));h.addWidget(action('Clear',self.clear_password));h.addStretch();body.addLayout(h);v.addWidget(box);v.addStretch()
    @safe
    def save_admin_profile(self):
        name=self.admin_name.text();email=self.admin_email.text();user=dict(self.user)
        password=self.admin_profile_password.text();self.admin_profile_password.clear()
        def done(saved):
            saved_name,saved_email=saved
            self.user.update(full_name=saved_name,email=saved_email)
            if self.admin_name.text()==name:self.admin_name.setText(saved_name)
            if self.admin_email.text()==email:self.admin_email.setText(saved_email)
            self.side_welcome.setText(saved_name)
            self.dashboard_greeting.setText('Welcome back, '+saved_name)
        self.submit_action(lambda:db.update_admin_profile(user,name,email,password),done,message='Admin profile saved.')
    def clear_password(self):
        self.old_password.clear();self.new_password.clear();self.confirm_password.clear()
    @safe
    def change_password(self):
        old=self.old_password.text();new=self.new_password.text()
        if new!=self.confirm_password.text():raise ValueError('New passwords do not match.')
        self.submit_action(lambda:db.change_password(self.user,old,new),lambda _:self.clear_password(),message='Password updated successfully.')
    def setup_history(self):
        v=self.add_tab('Attendance & reports');v.addWidget(text_hint('Review attendance records, filter by course and export a report.'))
        box,body=section('Attendance records','Choose a course to narrow the results.')
        bar=QHBoxLayout();self.history_courses=QComboBox();self.history_courses.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);self.history_courses.setMinimumContentsLength(8);self.history_courses.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed);self.history_courses.addItem('All courses',None)
        for r in db.courses(self.user):self.history_courses.addItem(course_label(r),r['course_id'])
        bar.addWidget(self.history_courses,1);self.history_status=QComboBox();self.history_status.addItems(['All statuses','PRESENT','ABSENT','LATE']);bar.addWidget(self.history_status);body.addLayout(bar)
        self.history_range=QCheckBox('Filter by date');self.history_from=QDateEdit(QDate.currentDate().addDays(-30));self.history_to=QDateEdit(QDate.currentDate());self.history_from.setCalendarPopup(True);self.history_to.setCalendarPopup(True)
        bar=QHBoxLayout();bar.addWidget(self.history_range);bar.addWidget(self.history_from);bar.addWidget(self.history_to);body.addLayout(bar)
        bar=QHBoxLayout();bar.addWidget(action('↻ Load records',self.refresh_history));bar.addWidget(action('Export CSV',self.export_csv));bar.addStretch();body.addLayout(bar)
        self.summary_labels={};stats=QHBoxLayout();stats.setSpacing(12)
        for key,label in [('present','Present'),('absent','Absent'),('late','Late'),('total','Total records')]:
            tile=QFrame();tile.setObjectName('statCard');lay=QVBoxLayout(tile);lay.setContentsMargins(14,10,14,10);caption=QLabel(label);caption.setObjectName('statLabel');lay.addWidget(caption);value=QLabel('0');value.setObjectName('statValue');value.setStyleSheet('font-size:21px');lay.addWidget(value);self.summary_labels[key]=value;stats.addWidget(tile,1)
        body.addLayout(stats);self.hist=table(['Date','Course','Roll number','Student','Status','Method']);self.hist.setMinimumHeight(240);body.addWidget(self.hist);v.addWidget(box)
        if self.user['role']=='TEACHER':
            correction,details=section('Correct attendance','Select a record above, choose its new status and enter a reason.')
            line=QHBoxLayout();self.correct_status=QComboBox();self.correct_status.addItems(['PRESENT','ABSENT','LATE']);self.correct_remarks=field('Reason for correction');line.addWidget(self.correct_status);line.addWidget(self.correct_remarks,1);line.addWidget(button('Save correction',self.correct_record));details.addLayout(line);v.addWidget(correction)
        v.addStretch();self.refresh_history()
    @safe
    def refresh_history(self):
        start=self.history_from.date().toPython() if self.history_range.isChecked() else None;end=self.history_to.date().toPython() if self.history_range.isChecked() else None
        self.history_rows=db.attendance(self.user,self.history_courses.currentData(),start,end);status=self.history_status.currentText();self.history_rows=[r for r in self.history_rows if status=='All statuses' or r['status']==status];fill(self.hist,self.history_rows,['session_date','course_code','roll_number','full_name','status','check_in_method'])
        for key in ('present','absent','late'):self.summary_labels[key].setText(str(sum(1 for r in self.history_rows if r['status']==key.upper())))
        self.summary_labels['total'].setText(str(len(self.history_rows)))
    @safe
    def correct_record(self):
        row=self.hist.currentRow()
        if row<0 or row>=len(self.history_rows):raise ValueError('Select an attendance record first.')
        record=self.history_rows[row];args=(self.user,record['attendance_id'],self.correct_status.currentText(),self.correct_remarks.text());self.submit_action(lambda:db.correct_attendance(*args),lambda _:(self.correct_remarks.clear(),self.refresh_history()),message='Attendance corrected.')
    def setup_correction_requests(self):
        v=self.add_tab('Correction requests');v.addWidget(text_hint('Track and review attendance correction requests.'))
        if self.user['role']=='STUDENT':
            box,body=section('Request a correction','First select a record in My Attendance, then enter the requested status and reason.')
            line=QHBoxLayout();self.request_status=QComboBox();self.request_status.addItems(['PRESENT','ABSENT','LATE']);self.request_reason=field('Reason for your request');line.addWidget(self.request_status);line.addWidget(self.request_reason,1);line.addWidget(button('Submit request',self.submit_correction_request));body.addLayout(line);v.addWidget(box)
            headers=['Course','Date','Requested','Reason','Status','Submitted'];self.request_columns=['course_code','session_date','requested_status','reason','status','created_at']
        else:
            headers=['Course','Roll number','Student','Date','Current','Requested','Reason','Status'];self.request_columns=['course_code','roll_number','full_name','session_date','current_status','requested_status','reason','status']
        box,body=section('Requests');self.correction_table=table(headers);self.correction_table.setMinimumHeight(220);body.addWidget(self.correction_table)
        bar=QHBoxLayout();bar.addWidget(action('Refresh',self.refresh_correction_requests))
        if self.user['role']=='TEACHER':bar.addWidget(action('Approve',lambda:self.resolve_correction_request(True),'success'));bar.addWidget(action('Reject',lambda:self.resolve_correction_request(False),'danger'))
        bar.addStretch();body.addLayout(bar);v.addWidget(box);v.addStretch();self.refresh_correction_requests()
    @safe
    def refresh_correction_requests(self):
        self.correction_rows=db.correction_requests(self.user);fill(self.correction_table,self.correction_rows,self.request_columns)
    @safe
    def submit_correction_request(self):
        row=self.hist.currentRow()
        if row<0 or row>=len(self.history_rows):raise ValueError('Select a record in My Attendance first.')
        args=(self.user,self.history_rows[row]['attendance_id'],self.request_status.currentText(),self.request_reason.text());self.submit_action(lambda:db.request_attendance_correction(*args),lambda _:(self.request_reason.clear(),self.refresh_correction_requests()),message='Request submitted to your teacher.')
    @safe
    def resolve_correction_request(self,approve):
        row=self.correction_table.currentRow()
        if row<0 or row>=len(self.correction_rows):raise ValueError('Select a request first.')
        request_id=self.correction_rows[row]['request_id'];self.submit_action(lambda:db.resolve_attendance_request(self.user,request_id,approve),lambda _:(self.refresh_correction_requests(),self.refresh_history()),message='Request approved.' if approve else 'Request rejected.')
    def setup_reports(self):
        v=self.add_tab('Course reports');v.addWidget(text_hint('Review attendance totals and percentages for each enrolled student.'))
        box,body=section('Course attendance report','Choose a course and generate its current summary.');bar=QHBoxLayout();self.report_course=QComboBox();load_combo(self.report_course,db.courses(self.user),course_label,'course_id');bar.addWidget(self.report_course,1);body.addLayout(bar)
        bar=QHBoxLayout();bar.addWidget(button('Generate report',self.generate_report));bar.addWidget(action('Export CSV',self.export_course_report));bar.addStretch();body.addLayout(bar)
        self.report_table=table(['Roll number','Student','Sessions','Present','Absent','Late','Attendance %']);self.report_table.setMinimumHeight(260);body.addWidget(self.report_table);self.report_rows=[];self.report_course_id=None;v.addWidget(box);v.addStretch()
    @safe
    def generate_report(self):
        course=self.report_course.currentData()
        if not course:raise ValueError('Select a course first.')
        self.report_rows=db.course_summary(self.user,course);self.report_course_id=course;fill(self.report_table,self.report_rows,['roll_number','full_name','total_sessions','present_count','absent_count','late_count','attendance_pct'])
    @safe
    def export_course_report(self):
        import csv
        if not self.report_rows or self.report_course_id!=self.report_course.currentData():raise ValueError('Generate a report for the selected course first.')
        path,_=QFileDialog.getSaveFileName(self,'Export course report','course_report.csv','CSV (*.csv)')
        if path:
            with open(path,'w',newline='',encoding='utf-8-sig') as f:
                wr=csv.writer(f);wr.writerow(['Roll number','Student','Sessions','Present','Absent','Late','Attendance %']);wr.writerows([[r.get(k) for k in ('roll_number','full_name','total_sessions','present_count','absent_count','late_count','attendance_pct')] for r in self.report_rows])
            alert(self,'Report exported.')
    @safe
    def export_csv(self):
        import csv
        p,_=QFileDialog.getSaveFileName(self,'Export attendance','attendance.csv','CSV (*.csv)')
        if p:
            with open(p,'w',newline='',encoding='utf-8-sig') as f:
                wr=csv.writer(f);wr.writerow(['Date','Course','Roll number','Student','Status','Method']);wr.writerows([[r.get(k) for k in ['session_date','course_code','roll_number','full_name','status','check_in_method']] for r in self.history_rows])
            alert(self,'Report exported.')
    def setup_admin(self):
        v=self.add_tab('Students & face enrollment');v.addWidget(text_hint('Search, add or edit students, then enroll their face using a camera or photo.'))
        box,body=section('Student directory')
        bar=QHBoxLayout();self.student_search=field('Search by name, roll number or email');self.student_search.textChanged.connect(self.filter_students);bar.addWidget(self.student_search,1);bar.addWidget(action('↻ Refresh',self.refresh_students));body.addLayout(bar)
        self.students_table=table(['Roll number','Full name','Department','Semester','Batch','Email','Face']);self.students_table.setMinimumHeight(205);self.students_table.itemSelectionChanged.connect(self.student_selected);body.addWidget(self.students_table);v.addWidget(box)
        box,body=section('Add / Edit Student','Select a student from the directory to edit; choose Clear to add someone new.')
        self.s_roll=field('e.g. 2024-SE-001');self.s_name=field('Full name');self.s_email=field('student@example.com');self.s_phone=field('Phone number (optional)')
        self.s_dept=QComboBox();load_combo(self.s_dept,db.departments(),lambda r:r['dept_name'],'dept_id');self.s_sem=QSpinBox();self.s_sem.setRange(1,8);self.s_year=QSpinBox();self.s_year.setRange(1990,date.today().year+1);self.s_year.setValue(date.today().year)
        grid=QGridLayout();grid.setHorizontalSpacing(16);grid.setVerticalSpacing(12)
        for i,(label,w) in enumerate([('Roll number *',self.s_roll),('Full name *',self.s_name),('Department',self.s_dept),('Semester',self.s_sem),('Email address',self.s_email),('Phone number',self.s_phone),('Batch year',self.s_year)]):grid.addWidget(form_cell(label,w),i//2,i%2)
        body.addLayout(grid);bar=QGridLayout();bar.setSpacing(8)
        for i,(text,fn,kind) in enumerate([('+ Add student',self.add_student,'primary'),('Add & capture face',self.add_student_and_capture,'success'),('Save changes',self.save_student,'secondary'),('Clear',self.clear_student_form,'secondary')]):bar.addWidget(action(text,fn,kind),i//2,i%2)
        body.addLayout(bar);bar=QGridLayout();bar.setSpacing(8)
        for i,(text,fn) in enumerate([('📷 Enroll face (camera)',self.enroll_face_camera),('Enroll face (photo)',self.enroll_face_file),('Batch enroll photos',self.batch_enroll)]):bar.addWidget(action(text,fn),i//2,i%2)
        body.addLayout(bar)
        bar=QHBoxLayout();bar.addWidget(action('Delete permanently',self.delete_student,'danger'));bar.addWidget(action('Withdraw face consent',self.withdraw_face_consent));bar.addStretch();body.addLayout(bar);v.addWidget(box)
        box,body=section('Create student login','Select an existing student above, then create their login credentials.')
        grid=QGridLayout();grid.setHorizontalSpacing(16);self.s_login_email=field('Login email');self.s_login_password=field('Minimum 8 characters',password=True);grid.addWidget(form_cell('Login email',self.s_login_email),0,0);grid.addWidget(form_cell('Password',self.s_login_password),0,1);body.addLayout(grid)
        bar=QHBoxLayout();bar.addWidget(action('Create login',self.create_login));bar.addStretch();body.addLayout(bar);v.addWidget(box);v.addStretch();self.selected_student_id=None;self.all_student_rows=[];self.student_rows=[];self.refresh_students()

        v=self.add_tab('Courses & enrollment');v.addWidget(text_hint('Create courses, assign teachers and manage student enrollment.'))
        box,body=section('Course directory','Select a course to manage it below.')
        self.course_table=table(['Code','Course','Department','Teacher','Semester']);self.course_table.setMinimumHeight(190);self.course_table.itemSelectionChanged.connect(self.course_table_selected);body.addWidget(self.course_table);v.addWidget(box)
        box,body=section('Course details','Fill out the form to create a course, or load a selected course to edit it.')
        self.course_code=field('e.g. CS-301');self.course_name=field('Enter course name');self.credits=QSpinBox();self.credits.setRange(1,6);self.sem=QSpinBox();self.sem.setRange(1,8)
        self.dept=QComboBox();load_combo(self.dept,db.departments(),lambda r:r['dept_name'],'dept_id');self.teacher=QComboBox();load_combo(self.teacher,db.teachers(),lambda r:r['full_name'],'user_id')
        grid=QGridLayout();grid.setHorizontalSpacing(16);grid.setVerticalSpacing(14)
        for i,(label,w) in enumerate([('Course code *',self.course_code),('Course name *',self.course_name),('Credit hours',self.credits),('Semester',self.sem),('Department',self.dept),('Assigned teacher',self.teacher)]):grid.addWidget(form_cell(label,w),i//2,i%2)
        body.addLayout(grid);buttons=QGridLayout();buttons.addWidget(button('+ Create course',self.create_course),0,0);buttons.addWidget(action('Save edits',self.save_course_edits),0,1);buttons.addWidget(action('Clear',self.clear_course_form),1,0);body.addLayout(buttons);v.addWidget(box)
        box,body=section('Course selection & enrollment','Select a course and student to manage their enrollment.')
        self.admin_course=QComboBox();self.admin_student=QComboBox();grid=QGridLayout();grid.setHorizontalSpacing(16);grid.addWidget(form_cell('Selected course',self.admin_course),0,0);grid.addWidget(form_cell('Selected student',self.admin_student),0,1);body.addLayout(grid)
        buttons=QGridLayout();buttons.setSpacing(8)
        for i,(text,fn,kind) in enumerate([('Enroll student',self.enroll,'success'),('Bulk enroll',self.enroll_all,'secondary'),('Unenroll',self.unenroll,'secondary'),('Load course to edit',self.edit_course,'secondary')]):buttons.addWidget(action(text,fn,kind),i//2,i%2)
        body.addLayout(buttons)
        buttons=QHBoxLayout();buttons.addWidget(action('Delete permanently',self.delete_course,'danger'));buttons.addWidget(action('↻ Refresh',self.refresh_admin));buttons.addStretch();body.addLayout(buttons);v.addWidget(box);v.addStretch();self.editing_course_id=None;self.refresh_admin()

        v=self.add_tab('Teachers');v.addWidget(text_hint('Register teachers and manage their profiles and course access.'))
        box,body=section('Teacher directory');self.teacher_table=table(['Teacher name','Email','Department']);self.teacher_table.setMinimumHeight(210);self.teacher_table.itemSelectionChanged.connect(self.teacher_selected);body.addWidget(self.teacher_table)
        h=QHBoxLayout();h.addStretch();h.addWidget(action('↻ Refresh',self.refresh_teachers));body.addLayout(h);v.addWidget(box)
        box,body=section('Register / Edit Teacher','Select a teacher to edit their name or department. Email and password are used when registering a new teacher.')
        self.t_name=field('Full name');self.t_email=field('teacher@example.com');self.t_password=field('Minimum 8 characters',password=True);self.t_dept=QComboBox();load_combo(self.t_dept,db.departments(),lambda r:r['dept_name'],'dept_id')
        grid=QGridLayout();grid.setHorizontalSpacing(16);grid.setVerticalSpacing(12)
        for i,(label,w) in enumerate([('Full name *',self.t_name),('Email *',self.t_email),('Password *',self.t_password),('Department',self.t_dept)]):grid.addWidget(form_cell(label,w),i//2,i%2)
        body.addLayout(grid);h=QGridLayout();h.setSpacing(8)
        for i,(text,fn,kind) in enumerate([('+ Register teacher',self.register_teacher,'primary'),('Save changes',self.save_teacher,'secondary'),('Clear',self.clear_teacher_form,'secondary'),('Delete permanently',self.delete_teacher,'danger')]):h.addWidget(action(text,fn,kind),i//2,i%2)
        body.addLayout(h);v.addWidget(box);v.addStretch();self.selected_teacher_id=None;self.teacher_rows=[];self.refresh_teachers()

        v=self.add_tab('Password resets');v.addWidget(text_hint('Students and teachers recover access through a code sent to their registered email. Configure the sender once on this computer.'))
        box,body=section('Email recovery','Gmail verification codes expire after 10 minutes. Only a verified code can reset a password.');body.addWidget(button('Gmail settings & test email',self.gmail_settings));v.addWidget(box)
        box,body=section('Legacy requests','Requests submitted before email recovery was enabled. Verify identity directly before approving a legacy request.');self.reset_table=table(['Role','Name','Email','Requested']);self.reset_table.setMinimumHeight(260);body.addWidget(self.reset_table)
        h=QHBoxLayout();h.addWidget(action('Approve',lambda:self.resolve_reset(True),'success'));h.addWidget(action('Reject',lambda:self.resolve_reset(False),'danger'));h.addStretch();h.addWidget(action('↻ Refresh',self.refresh_resets));body.addLayout(h);v.addWidget(box);v.addStretch();self.refresh_resets()
        v=self.add_tab('Teacher approvals');v.addWidget(text_hint('Review teacher signups before granting access.'))
        box,body=section('Pending teacher requests','Verify the applicant through your institution before approval.')
        self.signup_requests=table(['Name','Email','Department','Requested']);self.signup_requests.setMinimumHeight(240);body.addWidget(self.signup_requests)
        bar=QHBoxLayout();bar.addWidget(action('Approve',lambda:self.resolve_signup(True),'success'));bar.addWidget(action('Reject',lambda:self.resolve_signup(False),'danger'));bar.addWidget(action('Refresh',self.refresh_signups));bar.addStretch();body.addLayout(bar);v.addWidget(box);v.addStretch();self.refresh_signups()
        from .hardware_ui import HardwarePanel
        from .operations_ui import ClassesPanel,OperationsPanel
        v=self.add_tab('Hardware & cameras');self.hardware_panel=HardwarePanel(self.user,self);v.addWidget(self.hardware_panel)
        v=self.add_tab('Classes & sections');self.classes_panel=ClassesPanel(self.user,self);v.addWidget(self.classes_panel)
        v=self.add_tab('Settings, audit & diagnostics');self.operations_panel=OperationsPanel(self.user,self);v.addWidget(self.operations_panel)
    @safe
    def refresh_signups(self):
        self.signup_rows=db.pending_teacher_signups(self.user);fill(self.signup_requests,self.signup_rows,['full_name','email','department','created_at'])
    @safe
    def resolve_signup(self,approve):
        i=self.signup_requests.currentRow()
        if i<0 or i>=len(self.signup_rows):raise ValueError('Select a request first.')
        request_id=self.signup_rows[i]['request_id'];self.submit_action(lambda:db.resolve_teacher_signup(self.user,request_id,approve),lambda _:(self.refresh_signups(),self.refresh_teachers(),self.refresh_admin()),message='Request approved.' if approve else 'Request rejected.')
    @safe
    def refresh_teachers(self):
        self.clear_teacher_form();self.teacher_rows=db.teachers()
        with QSignalBlocker(self.teacher_table):fill(self.teacher_table,self.teacher_rows,['full_name','email','department'])
    def teacher_selected(self):
        row=self.teacher_table.currentRow()
        if not self.teacher_table.selectionModel().hasSelection() or row<0 or row>=len(self.teacher_rows):return
        t=self.teacher_rows[row];self.selected_teacher_id=t['user_id'];self.t_name.setText(t['full_name']);self.t_email.setText(t['email']);self.t_email.setReadOnly(True);self.t_password.clear();self.t_password.setEnabled(False)
        idx=self.t_dept.findText(t['department'] or '')
        if idx>=0:self.t_dept.setCurrentIndex(idx)
    def clear_teacher_form(self):
        self.teacher_table.clearSelection();self.selected_teacher_id=None;self.t_name.clear();self.t_email.setReadOnly(False);self.t_email.clear();self.t_password.setEnabled(True);self.t_password.clear();self.t_dept.setCurrentIndex(0)
    @safe
    def register_teacher(self):
        if self.selected_teacher_id:raise ValueError('Choose Clear before registering a new teacher.')
        args=(self.t_name.text(),self.t_email.text(),self.t_password.text(),self.t_dept.currentText())
        self.submit_action(lambda:db.signup_teacher(*args,actor=self.user),lambda _:(self.clear_teacher_form(),self.refresh_teachers(),self.refresh_admin()),message='Teacher registered successfully.')
    @safe
    def save_teacher(self):
        if not self.selected_teacher_id:raise ValueError('Select a teacher first.')
        args=(self.selected_teacher_id,self.t_name.text(),self.t_dept.currentText());self.submit_action(lambda:db.update_teacher(*args,actor=self.user),lambda _:(self.clear_teacher_form(),self.refresh_teachers(),self.refresh_admin()),message='Teacher updated.')
    @safe
    def delete_teacher(self):
        if not self.selected_teacher_id:raise ValueError('Select a teacher first.')
        if QMessageBox.question(self,'Delete teacher','Permanently delete this teacher AND their assigned courses, enrollments, attendance and check-in history? This cannot be undone.')!=QMessageBox.StandardButton.Yes:return
        teacher=self.selected_teacher_id;self.submit_action(lambda:db.delete_teacher_permanently(teacher,actor=self.user),lambda _:(self.clear_teacher_form(),self.refresh_teachers(),self.refresh_admin()),message='Teacher permanently deleted.')
    @safe
    def edit_course(self):
        cid=self.admin_course.currentData()
        if not cid:raise ValueError('Select a course.')
        c=db.one('SELECT * FROM courses WHERE course_id=:id',{'id':cid});self.editing_course_id=cid;self.course_code.setText(c['course_code']);self.course_name.setText(c['course_name']);self.credits.setValue(c['credit_hours']);self.sem.setValue(c['semester']);self.dept.setCurrentIndex(self.dept.findData(c['dept_id']));self.teacher.setCurrentIndex(self.teacher.findData(c['teacher_id']))
        self.tabs.currentWidget().ensureWidgetVisible(self.course_code);alert(self,'Edit the course form above, then choose Save course edits.')
    @safe
    def save_course_edits(self):
        cid=self.admin_course.currentData()
        if not cid:raise ValueError('Select a course.')
        if self.editing_course_id!=cid:raise ValueError('Load the selected course before saving edits.')
        args=(cid,self.course_code.text(),self.course_name.text(),self.credits.value(),self.dept.currentData(),self.teacher.currentData(),self.sem.value());self.submit_action(lambda:db.update_course(*args,actor=self.user),lambda _:self.refresh_admin(),message='Course updated.')
    @safe
    def unenroll(self):
        if QMessageBox.question(self,'Confirm','Unenroll selected student from selected course?')==QMessageBox.StandardButton.Yes:
            course,student=self.admin_course.currentData(),self.admin_student.currentData();self.submit_action(lambda:db.unenroll_student(course,student,actor=self.user),message='Enrollment removed if present.')
    def student_selected(self):
        row=self.students_table.currentRow()
        if not self.students_table.selectionModel().hasSelection() or row<0 or row>=len(self.student_rows):return
        item=self.student_rows[row];full=db.one('SELECT * FROM students WHERE student_id=:id',{'id':item['student_id']})
        if not full:return
        self.selected_student_id=item['student_id'];self.s_roll.setText(full['roll_number']);self.s_roll.setReadOnly(True);self.s_name.setText(full['full_name']);self.s_email.setText(full['email'] or '');self.s_phone.setText(full['phone'] or '')
        self.s_dept.setCurrentIndex(self.s_dept.findData(full['dept_id']));self.s_sem.setValue(full['semester']);self.s_year.setValue(full['batch_year']);self.s_login_email.setText(full['email'] or '');self.s_login_password.clear()
    def clear_student_form(self):
        self.students_table.clearSelection();self.selected_student_id=None;self.s_roll.setReadOnly(False);self.s_roll.clear();self.s_name.clear();self.s_email.clear();self.s_phone.clear();self.s_dept.setCurrentIndex(0);self.s_sem.setValue(1);self.s_year.setValue(date.today().year);self.s_login_email.clear();self.s_login_password.clear()
    def select_student_by_id(self,student_id):
        for i,r in enumerate(self.student_rows):
            if r['student_id']==student_id:self.students_table.selectRow(i);self.student_selected();return
    def _add_student_record(self):
        if self.selected_student_id:raise ValueError('Choose Clear before adding a new student.')
        matches=db.students_for_roll(self.s_roll.text())
        if any(r['is_active'] for r in matches):raise ValueError('An active student already uses this roll number.')
        sid=db.add_student(self.s_name.text(),self.s_roll.text(),self.s_email.text(),self.s_phone.text(),self.s_dept.currentData(),self.s_sem.value(),self.s_year.value(),actor=self.user)
        self.student_search.clear();self.refresh_students();self.refresh_admin();self.select_student_by_id(sid);return sid
    @safe
    def add_student(self):
        self.create_student_async(False)
    @safe
    def add_student_and_capture(self):
        self.create_student_async(True)
    def create_student_async(self,capture):
        if self.selected_student_id:raise ValueError('Choose Clear before adding a new student.')
        args=(self.s_name.text(),self.s_roll.text(),self.s_email.text(),self.s_phone.text(),self.s_dept.currentData(),self.s_sem.value(),self.s_year.value())
        def done(sid):
            self._select_after_refresh=sid;self.student_search.clear();self.refresh_students();self.refresh_admin()
            if capture:self._capture_student_face(sid,args[0])
        self.submit_action(lambda:db.add_student(*args,actor=self.user),done,message='Student added successfully.')
    @safe
    def save_student(self):
        if not self.selected_student_id:raise ValueError('Select a student first.')
        sid=self.selected_student_id;args=(sid,self.s_name.text(),self.s_email.text(),self.s_phone.text(),self.s_dept.currentData(),self.s_sem.value(),self.s_year.value())
        self.submit_action(lambda:db.update_student(*args,actor=self.user),lambda _:(setattr(self,'_select_after_refresh',sid),self.refresh_students(),self.refresh_admin()),message='Student updated.')
    @safe
    def delete_student(self):
        if not self.selected_student_id:raise ValueError('Select a student first.')
        prompt=('Permanently delete this student? Their attendance, course enrollments, login and reset requests will also be deleted. This cannot be undone.')
        if QMessageBox.question(self,'Delete student permanently',prompt)!=QMessageBox.StandardButton.Yes:return
        from .face import FACE_DIR,LEGACY_FACE_DIR
        sid=self.selected_student_id
        def remove():
            db.delete_student_permanently(sid,actor=self.user)
            for path in (FACE_DIR/(sid+'.template'),FACE_DIR/(sid+'.image'),LEGACY_FACE_DIR/(sid+'.png')):path.unlink(missing_ok=True)
        self.submit_action(remove,lambda _:(self.clear_student_form(),self.refresh_students(),self.refresh_admin()),message='Student and related records deleted.')
    def _capture_student_face(self,student_id,name):
        if not self.confirm_biometric_consent(student_id):return False
        dialog=CameraCaptureDialog(self,name)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return False
        raw=dialog.capture_bytes
        def enroll():
            from .privacy import record_consent
            record_consent(self.user,student_id,True);FaceEngine().save_reference_bytes(student_id,raw)
        self.submit_action(enroll,lambda _:(setattr(self,'_select_after_refresh',student_id),self.refresh_students()),message='Face enrolled successfully.');return True
    def confirm_biometric_consent(self,student_id):
        from . import privacy
        if QMessageBox.question(self,'Optional biometric enrollment',privacy.NOTICE)!=QMessageBox.StandardButton.Yes:return False
        return True
    @safe
    def withdraw_face_consent(self):
        if not self.selected_student_id:raise ValueError('Select a student first.')
        if QMessageBox.question(self,'Withdraw biometric consent','Disable face attendance and remove this student’s local face template? Manual attendance remains available.')!=QMessageBox.StandardButton.Yes:return
        from .privacy import revoke
        sid=self.selected_student_id;self.submit_action(lambda:revoke(self.user,sid),lambda _:self.refresh_students(),message='Consent withdrawn; biometric reference removed.')
    @safe
    def enroll_face_camera(self):
        if not self.selected_student_id:raise ValueError('Select a student first.')
        self._capture_student_face(self.selected_student_id,self.s_name.text())
    @safe
    def enroll_face_file(self):
        if not self.selected_student_id:raise ValueError('Select a student first.')
        path,_=QFileDialog.getOpenFileName(self,'Select a face photo','','Images (*.png *.jpg *.jpeg *.bmp)')
        if not path:return
        sid=self.selected_student_id
        if not self.confirm_biometric_consent(sid):return
        def enroll():
            from .privacy import record_consent
            record_consent(self.user,sid,True);FaceEngine().save_reference(sid,path)
        self.submit_action(enroll,lambda _:(setattr(self,'_select_after_refresh',sid),self.refresh_students()),message='Face enrolled successfully.')
    @safe
    def delete_course(self):
        course=self.admin_course.currentData()
        if not course:raise ValueError('Select a course first.')
        if QMessageBox.question(self,'Delete course','Permanently delete this course AND its enrollments, attendance and check-in history? This cannot be undone.')!=QMessageBox.StandardButton.Yes:return
        self.submit_action(lambda:db.delete_course_permanently(course,actor=self.user),lambda _:self.refresh_admin(),message='Course permanently deleted.')
    @safe
    def create_login(self):
        if not self.selected_student_id:raise ValueError('Select a student first.')
        args=(self.selected_student_id,self.s_login_email.text(),self.s_login_password.text());self.submit_action(lambda:db.create_student_login(*args,actor=self.user),lambda _:self.s_login_password.clear(),message='Student login created.')
    @safe
    def gmail_settings(self):
        from .recovery_ui import GmailSettingsDialog
        GmailSettingsDialog(self,self.user).exec()

    @safe
    def refresh_resets(self):
        self.reset_rows=db.pending_resets();fill(self.reset_table,self.reset_rows,['user_type','user_name','user_email','requested_at'])
    @safe
    def resolve_reset(self,approve):
        row=self.reset_table.currentRow()
        if row<0:raise ValueError('Select a request first.')
        request_id=self.reset_rows[row]['request_id'];self.submit_action(lambda:db.resolve_reset(request_id,approve,actor=self.user),lambda _:self.refresh_resets(),message='Request updated.')
    @safe
    def refresh_students(self):
        self.all_student_rows=db.students();self.filter_students()
        sid=getattr(self,'_select_after_refresh',None)
        if sid:self._select_after_refresh=None;QTimer.singleShot(0,lambda:self.select_student_by_id(sid))
    def filter_students(self):
        self.clear_student_form();term=self.student_search.text().strip().casefold()
        self.student_rows=[r for r in self.all_student_rows if not term or any(term in str(r.get(k) or '').casefold() for k in ('roll_number','full_name','email'))]
        display=[dict(r,face_status='Enrolled' if r['face_enrolled'] else 'Not enrolled') for r in self.student_rows]
        with QSignalBlocker(self.students_table):fill(self.students_table,display,['roll_number','full_name','dept_name','semester','batch_year','email','face_status'])
    @safe
    def batch_enroll(self):
        d=BatchEnrollment(self);d.exec();self.refresh_students()
    @safe
    def refresh_admin(self):
        self.editing_course_id=None;self.course_rows=db.courses()
        with QSignalBlocker(self.course_table):
            self.course_table.clearSelection();fill(self.course_table,self.course_rows,['course_code','course_name','dept_name','teacher_name','semester'])
        load_combo(self.admin_course,self.course_rows,course_label,'course_id');load_combo(self.admin_student,db.students(),student_label,'student_id');load_combo(self.teacher,db.teachers(),lambda r:r['full_name'],'user_id')
    def course_table_selected(self):
        row=self.course_table.currentRow()
        if self.course_table.selectionModel().hasSelection() and row>=0 and hasattr(self,'course_rows') and row<len(self.course_rows) and hasattr(self,'admin_course'):
            selected=self.course_rows[row];self.admin_course.setCurrentIndex(self.admin_course.findData(selected['course_id']))
            c=db.one('SELECT * FROM courses WHERE course_id=:id',{'id':selected['course_id']})
            if c:
                self.editing_course_id=selected['course_id'];self.course_code.setText(c['course_code']);self.course_name.setText(c['course_name']);self.credits.setValue(c['credit_hours']);self.sem.setValue(c['semester']);self.dept.setCurrentIndex(self.dept.findData(c['dept_id']));self.teacher.setCurrentIndex(self.teacher.findData(c['teacher_id']))
    def clear_course_form(self):
        self.course_table.clearSelection();self.editing_course_id=None;self.course_code.clear();self.course_name.clear();self.credits.setValue(1);self.sem.setValue(1);self.dept.setCurrentIndex(0);self.teacher.setCurrentIndex(0)
    @safe
    def enroll_all(self):
        course=self.admin_course.currentData()
        if not course:raise ValueError('Select a course first.')
        if QMessageBox.question(self,'Confirm enrollment','Enroll all active students whose department and semester match this course?')==QMessageBox.StandardButton.Yes:
            self.submit_action(lambda:db.enroll_all_students(course,actor=self.user),lambda count:self.statusBar().showMessage(f'{count} student(s) enrolled.',8000),message='Class enrollment updated.')
    @safe
    def create_course(self):
        args=(self.course_code.text(),self.course_name.text(),self.credits.value(),self.dept.currentData(),self.teacher.currentData(),self.sem.value());self.submit_action(lambda:db.add_course(*args,actor=self.user),lambda _:(self.clear_course_form(),self.refresh_admin()),message='Course created.')
    @safe
    def enroll(self):
        course,student=self.admin_course.currentData(),self.admin_student.currentData();self.submit_action(lambda:db.enroll_student(course,student,actor=self.user),message='Student enrolled successfully.')
    def setup_teacher(self):
        v=self.add_tab('Mark attendance');v.addWidget(text_hint('Select your course and date, then load the enrolled students.'))
        box,body=section('Attendance session')
        h=QHBoxLayout();self.mark_course=QComboBox();load_combo(self.mark_course,db.courses(self.user),course_label,'course_id');h.addWidget(form_cell('Course',self.mark_course),2)
        self.day=QDateEdit(QDate.currentDate());self.day.setCalendarPopup(True);h.addWidget(form_cell('Session date',self.day),1);body.addLayout(h)
        h=QHBoxLayout();h.addWidget(button('Load students',self.load_roster));h.addWidget(action('All present',lambda:self.set_all('PRESENT'),'success'));h.addWidget(action('All absent',lambda:self.set_all('ABSENT')));h.addStretch();body.addLayout(h);v.addWidget(box)
        box,body=section('Student attendance','Existing Face/QR records are preloaded. Choose statuses to add or change, then save.')
        self.roster_rows=[];self.roster_original={};self.roster_snapshot={};self.loaded_course_id=None;self.loaded_session_date=None;self.roster=table(['Roll number','Student','Status']);self.roster.setMinimumHeight(260);body.addWidget(self.roster)
        h=QHBoxLayout();h.addStretch();h.addWidget(button('Save attendance',self.save_roster));body.addLayout(h);v.addWidget(box);v.addStretch()

        v=self.add_tab('Multi-face camera')
        box=QFrame();box.setObjectName('sectionCard');body=QVBoxLayout(box);body.setContentsMargins(14,10,14,10);body.setSpacing(8)
        top=QHBoxLayout();self.camera_session=QLabel();self.camera_session.setObjectName('helperText');self.camera_session.setWordWrap(True);top.addWidget(self.camera_session,1)
        top.addWidget(action('Change course or date',lambda:self.navigate_to('Mark attendance')));body.addLayout(top)
        self.mark_course.currentIndexChanged.connect(self.update_session_context);self.day.dateChanged.connect(self.update_session_context)
        self.camera_source=field('0, 1 or network camera URL');self.camera_source.setText('0');body.addWidget(form_cell('Camera source',self.camera_source));row=QGridLayout()
        self.camera_test_button=action('Test camera',self.test_camera);row.addWidget(self.camera_test_button,0,0)
        self.camera_start_button=action('Start attendance',self.start_camera,'success');row.addWidget(self.camera_start_button,0,1)
        self.camera_stop_button=action('Stop',self.stop_camera);self.camera_stop_button.setEnabled(False);row.addWidget(self.camera_stop_button,1,0)
        self.camera_full_button=action('Enlarge',self.open_camera_fullscreen);row.addWidget(self.camera_full_button,1,1);body.addLayout(row)
        self.saved_camera=QComboBox();self.saved_camera.addItem('Laptop camera / local index',None);body.addWidget(form_cell('Saved camera (configured by your administrator)',self.saved_camera));body.addWidget(action('Refresh saved cameras',self.refresh_saved_cameras))
        row=QHBoxLayout();self.camera_mirror=QCheckBox('Mirror preview');self.camera_mirror.setChecked(settings.mirror_preview_enabled());self.camera_mirror.toggled.connect(self.on_camera_mirror_changed);row.addWidget(self.camera_mirror)
        self.camera_status=QLabel('Ready to start');self.camera_status.setObjectName('helperText');self.camera_status.setWordWrap(True);row.addWidget(self.camera_status,1);body.addLayout(row);v.addWidget(box)
        self.camera_confirmation=QLabel('Waiting for attendance confirmations.');self.camera_confirmation.setObjectName('attendanceSuccess');self.camera_confirmation.setStyleSheet('padding:7px 12px;font-size:14px');self.camera_confirmation.setWordWrap(True);v.addWidget(self.camera_confirmation)
        stage=QHBoxLayout();stage.setSpacing(14);self.preview=CameraPreview();stage.addWidget(self.preview,4)
        side,details=section('Live activity','Each confirmed student appears here after Oracle saves attendance.');side.setMinimumWidth(235);side.setMaximumWidth(310)
        self.camera_events=QListWidget();self.camera_events.setMinimumHeight(260);details.addWidget(self.camera_events,1)
        details.addWidget(text_hint('Green: saved\nAmber: verifying or saving\nRed: unknown or uncertain'))
        stage.addWidget(side,1);v.addLayout(stage,1)
        box,body=section('Session roster','Face, QR and manual records for the selected course and date.')
        self.camera_roster_summary=QLabel('Select a course and refresh the roster.');self.camera_roster_summary.setObjectName('helperText');self.camera_roster_summary.setWordWrap(True);body.addWidget(self.camera_roster_summary)
        self.camera_roster=table(['Roll number','Student','Face enrolled','Attendance','Method']);self.camera_roster.setMinimumHeight(180);body.addWidget(self.camera_roster)
        body.addWidget(action('Refresh attendance roster',self.refresh_camera_roster));v.addWidget(box)
        self.camera_fullscreen=None;self.camera_full_preview=None
        self._face_roster_task=None;self._face_roster_timer=QTimer(self);self._face_roster_timer.setSingleShot(True);self._face_roster_timer.setInterval(500);self._face_roster_timer.timeout.connect(self.refresh_camera_roster_async)

        v=self.add_tab('QR attendance');v.addWidget(text_hint('Students sign in, verify their enrolled face and then submit attendance from their phone.'))
        box,body=section('Secure QR check-in','Select a course and date on Mark attendance. The QR code expires after 15 minutes.')
        self.qr_session=QLabel();self.qr_session.setObjectName('attendanceSuccess');self.qr_session.setWordWrap(True);body.addWidget(self.qr_session)
        body.addWidget(action('Change course or date',lambda:self.navigate_to('Mark attendance')))
        body.addWidget(text_hint('Generate QR reuses saved HTTPS settings and chooses an available port. Student phones should use the same Wi-Fi.'))
        from .config import load as load_config
        config=load_config()
        h=QHBoxLayout();self.qr_host=field('Wi-Fi IPv4 address or certificate hostname');self.qr_host.setText(config.qr_public_host);self.qr_port=QSpinBox();self.qr_port.setRange(1024,65535);self.qr_port.setValue(config.qr_port)
        h.addWidget(form_cell('HTTPS address',self.qr_host),3);h.addWidget(form_cell('Preferred port',self.qr_port),1);body.addLayout(h)
        qr_actions=QGridLayout()
        qr_actions.addWidget(button('Generate QR session',self.start_qr),0,0)
        qr_actions.addWidget(action('Stop QR session',self.stop_qr),0,1)
        qr_actions.addWidget(action('HTTPS setup',self.setup_qr_https),1,0)
        body.addLayout(qr_actions)
        self._qr_generation=0
        self.qr_endpoint=text_hint('');body.addWidget(self.qr_endpoint)
        self.qr_label=QLabel('No active session');self.qr_label.setObjectName('helperText');self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter);self.qr_label.setMinimumHeight(320);body.addWidget(self.qr_label);v.addWidget(box);v.addStretch();self.update_session_context()

    def update_session_context(self,*args):
        if self.qrserver or getattr(self,'_qr_starting',False):self.stop_qr()
        course=self.mark_course.currentText() if self.mark_course.currentData() else 'No course selected'
        text='Course: '+course+'    •    Date: '+self.day.date().toString('dd MMM yyyy')
        if hasattr(self,'camera_session'):self.camera_session.setText(text)
        if hasattr(self,'qr_session'):self.qr_session.setText(text)
        if hasattr(self,'camera_roster'):
            self.camera_roster.setRowCount(0);self.camera_roster_summary.setText('Session changed. Refresh the attendance roster.')
    @safe
    def refresh_camera_roster(self):
        course=self.mark_course.currentData()
        if not course:raise ValueError('Select a course on Mark attendance first.')
        students=db.course_students(course);records=db.session_attendance(self.user,course,self.day.date().toPython())
        self._display_camera_roster(students,records)
    def _display_camera_roster(self,students,records):
        enrolled_ids={student['student_id'] for student in students}
        records=[record for record in records if record['student_id'] in enrolled_ids]
        by_id={record['student_id']:record for record in records}
        rows=[]
        for student in students:
            record=by_id.get(student['student_id'],{})
            rows.append(dict(student,face_status='Enrolled' if student['face_enrolled'] else 'Not enrolled',status=record.get('status','Not marked'),method=record.get('check_in_method','—')))
        fill(self.camera_roster,rows,['roll_number','full_name','face_status','status','method'])
        present=sum(1 for r in records if r['status'] in ('PRESENT','LATE'))
        self.camera_roster_summary.setText(f'Enrolled: {len(students)}   •   Present / late: {present}   •   No record: {len(students)-len(records)}')
    def stop_qr(self):
        self._qr_generation=getattr(self,'_qr_generation',0)+1
        if self.qrserver:
            server=self.qrserver;self.qrserver=None
            self.submit_action(server.stop,message='QR session stopped.')
        self.qr_label.clear();self.qr_label.setText('No active session')
        self.qr_endpoint.clear()
    @safe
    def load_roster(self):
        self.loaded_course_id=self.mark_course.currentData();self.loaded_session_date=self.day.date().toPython()
        if not self.loaded_course_id:raise ValueError('Select a course first.')
        self.roster_rows=db.course_students(self.loaded_course_id)
        existing=db.session_attendance(self.user,self.loaded_course_id,self.loaded_session_date)
        self.roster_original={r['student_id']:r['status'] for r in existing};self.roster_snapshot={r['student_id']:(r['status'],r['check_in_method'],r['updated_at']) for r in existing};self.roster.setRowCount(len(self.roster_rows))
        for i,r in enumerate(self.roster_rows):
            self.roster.setItem(i,0,QTableWidgetItem(r['roll_number']));self.roster.setItem(i,1,QTableWidgetItem(r['full_name']))
            c=QComboBox();c.addItems(['Not marked','PRESENT','ABSENT','LATE']);c.setCurrentText(self.roster_original.get(r['student_id'],'Not marked'));self.roster.setCellWidget(i,2,c)
    def set_all(self,value):
        for i in range(self.roster.rowCount()):self.roster.cellWidget(i,2).setCurrentText(value)
    @safe
    def save_roster(self):
        day=self.day.date().toPython()
        if not self.roster_rows:raise ValueError('Load students before saving attendance.')
        if self.loaded_course_id!=self.mark_course.currentData() or self.loaded_session_date!=day:raise ValueError('Course or date changed. Load students again before saving.')
        entries=[(r['student_id'],self.roster.cellWidget(i,2).currentText()) for i,r in enumerate(self.roster_rows)]
        entries=[(sid,status) for sid,status in entries if status!='Not marked' and self.roster_original.get(sid)!=status]
        if not entries:raise ValueError('There are no new or changed attendance statuses to save.')
        course=self.mark_course.currentData();expected={sid:self.roster_snapshot.get(sid) for sid,_ in entries}
        self.submit_action(lambda:db.mark_bulk(self.user,course,day,entries,expected=expected),lambda _:self.load_roster(),message='Attendance saved successfully.')
    @safe
    def setup_qr_https(self):
        from .config import load,save_qr_tls
        from .qr import public_address
        from .qr_tls import create_reusable_certificate,tls_context
        config=load()
        dialog=QDialog(self);dialog.setWindowTitle('QR HTTPS setup');dialog.resize(650,420)
        layout=QVBoxLayout(dialog)
        layout.addWidget(text_hint('Use a campus certificate or create a reusable classroom certificate. Authorized phones trust the exported public certificate once. AMRS can then renew the server certificate when the Wi-Fi address changes.'))
        host=field('Wi-Fi address or certificate hostname');host.setText(self.qr_host.text() or config.qr_public_host)
        layout.addWidget(form_cell('QR address',host))
        cert=field('Certificate chain PEM file');cert.setText(config.qr_cert_file)
        key=field('Matching private key PEM file');key.setText(config.qr_key_file)
        for label,widget in [('Certificate',cert),('Private key',key)]:
            row=QHBoxLayout();row.addWidget(form_cell(label,widget),1)
            def browse(checked=False,w=widget):
                value,_=QFileDialog.getOpenFileName(dialog,'Choose PEM file','','PEM files (*.pem *.crt *.key);;All files (*)')
                if value:w.setText(value)
            row.addWidget(action('Browse',browse));layout.addLayout(row)
        notice=text_hint('The QR address must match the certificate. Share only the public .cer file with phones.')
        layout.addWidget(notice)
        def save():
            try:
                address=public_address(host.text()).lower()
                tls_context(cert.text().strip(),key.text().strip(),address)
                save_qr_tls(address,cert.text().strip(),key.text().strip())
            except (ValueError,OSError) as exc:
                notice.setText(str(exc));return
            self.qr_host.setText(address);self.stop_qr();dialog.accept()
        def generate():
            try:
                entered=host.text().strip()
                address=public_address(entered if entered!=config.qr_public_host else None).lower()
                pem,secret,public,fingerprint=create_reusable_certificate(address)
                host.setText(address);cert.setText(str(pem));key.setText(str(secret))
            except (ValueError,OSError) as exc:
                notice.setText(str(exc));return
            exported,_=QFileDialog.getSaveFileName(dialog,'Export public certificate for phones','AMRS-QR-Trust.cer','Certificate (*.cer)')
            if exported:
                try:
                    if Path(exported).resolve() in (pem.resolve(),secret.resolve()):
                        raise ValueError('Choose a different path for the public certificate.')
                    with open(exported,'xb') as output:output.write(public.read_bytes())
                except (OSError,ValueError):
                    notice.setText(f'Export failed. Use the public certificate at {public}');return
            notice.setText(f'Public certificate: {exported or public}\nSHA-256: {fingerprint}\nInstall and trust it on authorized phones, then save these settings.')
        row=QHBoxLayout()
        row.addWidget(action('Create reusable classroom certificate',generate))
        row.addWidget(button('Save HTTPS settings',save));layout.addLayout(row)
        dialog.exec()
    @safe
    def start_qr(self):
        import io,qrcode
        from .qr import QRServer
        if getattr(self,'_qr_starting',False):return
        course=self.mark_course.currentData()
        if not course:raise ValueError('Select a course first.')
        old=self.qrserver;self.qrserver=None;day=self.day.date().toPython();port=self.qr_port.value();host=self.qr_host.text();self._qr_starting=True
        generation=self._qr_generation;label=self.mark_course.currentText()
        self.qr_label.clear();self.qr_label.setText('Preparing secure QR session…')
        self.qr_endpoint.clear()
        def create():
            try:
                if old:old.stop()
                server=QRServer(self.user,course,day,port=port,public_host=host,course_label=label);buf=io.BytesIO()
                try:qrcode.make(server.url).save(buf,format='PNG')
                except Exception:server.stop();raise
                return server,buf.getvalue()
            except Exception as exc:return None,exc
        def done(result):
            self._qr_starting=False;server,raw=result
            if server is None:
                if generation==self._qr_generation:
                    self.qr_label.setText('No active session');self.statusBar().showMessage('Could not start secure QR.',8000);error(self,raw)
                return
            if generation!=self._qr_generation:
                self.submit_action(server.stop,message='QR session stopped.');return
            self.qrserver=server;pix=QPixmap();pix.loadFromData(raw);self.qr_label.setPixmap(pix.scaled(320,320,Qt.AspectRatioMode.KeepAspectRatio));self.qr_label.setToolTip(self.qrserver.url)
            self.qr_endpoint.setText(f'QR ready at {server.host}:{server.port} · Same Wi-Fi required')
        self.submit_action(create,done,message='Secure QR ready. Students must use the same Wi-Fi and trust the certificate.')
    @safe
    def test_camera(self):
        if (self.worker and self.worker.isRunning()) or (self.camera_probe and self.camera_probe.isRunning()):raise ValueError('Stop the current camera session first.')
        self.camera_probe=CameraProbeWorker(self.selected_camera_source(),mirror=self.camera_mirror.isChecked(),user=self.user);self.camera_probe.frame_ready.connect(self.show_frame);self.camera_events.clear();self.camera_probe.message.connect(self.on_camera_message);self.camera_probe.finished.connect(self.camera_finished);self.set_camera_controls(True);self.camera_probe.start()
    @safe
    def start_camera(self):
        if (self.worker and self.worker.isRunning()) or (self.camera_probe and self.camera_probe.isRunning()):raise ValueError('Stop the current camera session first.')
        if not self.mark_course.currentData():raise ValueError('Select a course first.')
        self.worker=CameraWorker(self.user,self.mark_course.currentData(),self.day.date().toPython(),self.selected_camera_source(),mirror=self.camera_mirror.isChecked());self.worker.frame_ready.connect(self.show_frame);self.camera_events.clear();self.camera_confirmation.setText('Waiting for attendance confirmations…');self.worker.message.connect(self.on_camera_message);self.worker.attendance_saved.connect(self.on_attendance_saved);self.worker.finished.connect(self.camera_finished);self.mark_course.setEnabled(False);self.day.setEnabled(False);self.set_camera_controls(True);self.worker.start()
    def refresh_saved_cameras(self):
        from .devices import list_devices
        def done(rows):
            self.saved_camera.clear();self.saved_camera.addItem('Laptop camera / local index',None)
            for row in rows:self.saved_camera.addItem(('SIMULATED — ' if row['device_type']=='mock' else '')+row['name'],row['device_id'])
            active=next((r['device_id'] for r in rows if r['is_active_source']),None)
            if active:self.saved_camera.setCurrentIndex(self.saved_camera.findData(active))
        self.submit_action(lambda:list_devices(self.user),done,message='Saved cameras refreshed.')
    def selected_camera_source(self):
        device_id=self.saved_camera.currentData()
        if device_id:return 'device:'+device_id
        source=self.camera_source.text().strip()
        if not source.isdecimal():raise ValueError('Use a local camera index, or ask your administrator to save and enable a network camera.')
        return source
    def on_camera_mirror_changed(self,checked):
        try:settings.save_mirror_preview(checked)
        except OSError:self.camera_status.setText('Preview changed, but the preference could not be saved.')
        if self.worker and self.worker.isRunning():self.worker.mirror=checked
        if self.camera_probe and self.camera_probe.isRunning():self.camera_probe.mirror=checked
    def on_camera_message(self,message):
        self.camera_status.setText(message);self.camera_events.addItem(datetime.now().strftime('%H:%M:%S')+'  '+message)
        while self.camera_events.count()>100:self.camera_events.takeItem(0)
        self.camera_events.scrollToBottom()
    def on_attendance_saved(self,name,roll):
        self.camera_confirmation.setText(f'Attendance marked successfully: {name} ({roll})')
        QApplication.beep()
        self._face_roster_timer.start()
    def set_camera_controls(self,running):
        self.camera_start_button.setEnabled(not running);self.camera_test_button.setEnabled(not running)
        self.camera_source.setEnabled(not running);self.camera_stop_button.setEnabled(running)
        self.saved_camera.setEnabled(not running)
    def camera_finished(self):
        self.mark_course.setEnabled(True);self.day.setEnabled(True);self.set_camera_controls(False)
    def stop_camera(self):
        active=False
        for worker in (self.worker,self.camera_probe):
            if worker and worker.isRunning():worker.running=False;worker.cancel_event.set();active=True
        if active:
            self.camera_stop_button.setEnabled(False);self.camera_status.setText('Stopping camera and completing pending saves…')
    def show_frame(self,frame):
        frame=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB);h,w=frame.shape[:2];image=QImage(frame.data,w,h,frame.strides[0],QImage.Format.Format_RGB888).copy();self.preview.setImage(image)
        if self.camera_full_preview is not None:self.camera_full_preview.setImage(image)
    def open_camera_fullscreen(self):
        if self.camera_fullscreen is not None:
            self.camera_fullscreen.raise_();self.camera_fullscreen.activateWindow();return
        dialog=QDialog(self);dialog.setWindowTitle('Face attendance — enlarged camera');dialog.resize(1100,720)
        layout=QVBoxLayout(dialog);layout.setContentsMargins(16,16,16,16)
        title=QLabel('Face attendance  •  Green: saved   Amber: verifying / saving   Red: unknown');title.setStyleSheet('color:#dce8ff;font-size:15px');layout.addWidget(title)
        preview=CameraPreview();layout.addWidget(preview,1);preview.setImage(self.preview.image)
        close=action('Close enlarged view',dialog.close);layout.addWidget(close)
        self.camera_fullscreen=dialog;self.camera_full_preview=preview
        def closed(*args):self.camera_full_preview=None;self.camera_fullscreen=None;dialog.deleteLater()
        dialog.finished.connect(closed);dialog.showMaximized()
    def refresh_camera_roster_async(self):
        if self._face_roster_task is not None:
            self._face_roster_timer.start();return
        course=self.mark_course.currentData();day=self.day.date().toPython()
        if not course:return
        def load():return db.course_students(course),db.session_attendance(self.user,course,day)
        task=BackgroundTask(load);self._face_roster_task=task
        def done(result):
            self._face_roster_task=None
            if self.mark_course.currentData()==course and self.day.date().toPython()==day:self._display_camera_roster(*result)
        def failed(exc):
            self._face_roster_task=None;self.camera_status.setText('Attendance saved. Roster refresh failed; use Refresh attendance roster.')
        task.signals.succeeded.connect(done,Qt.ConnectionType.QueuedConnection);task.signals.failed.connect(failed,Qt.ConnectionType.QueuedConnection);QThreadPool.globalInstance().start(task)

class CameraCaptureDialog(QDialog):
    """Capture one consenting student's face without storing a photo until confirmed."""
    def __init__(self,parent,student_name):
        super().__init__(parent);self.setWindowTitle('Enroll Face — Camera');self.resize(840,690);self.worker=None;self.latest=None;self.capture_bytes=None
        outer=QVBoxLayout(self);outer.setContentsMargins(24,22,24,22);outer.setSpacing(12)
        title=QLabel('Enroll Face — Camera');title.setObjectName('dialogTitle');outer.addWidget(title)
        outer.addWidget(text_hint('Student: '+student_name+'  •  Keep one face in the frame, facing the camera.'))
        bar=QHBoxLayout();self.source=field('0 for laptop or an RTSP/HTTP camera URL');self.source.setText('0');bar.addWidget(form_cell('Camera source',self.source),1);bar.addWidget(action('Open camera',self.open_camera));outer.addLayout(bar)
        self.mirror=QCheckBox('Mirror preview (move with me, like a selfie)');self.mirror.setChecked(settings.mirror_preview_enabled());self.mirror.toggled.connect(self.mirror_changed);outer.addWidget(self.mirror)
        self.preview=QLabel('Opening camera…');self.preview.setMinimumSize(640,360);self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter);self.preview.setStyleSheet('background:#202838;color:white;border-radius:8px');outer.addWidget(self.preview,1)
        self.status=QLabel('Starting camera…');self.status.setObjectName('helperText');self.status.setWordWrap(True);outer.addWidget(self.status)
        h=QHBoxLayout();h.addStretch();h.addWidget(action('Cancel',self.reject));self.capture=button('Capture face',self.capture_face);self.capture.setEnabled(False);h.addWidget(self.capture);outer.addLayout(h);QTimer.singleShot(0,self.open_camera)
    @safe
    def open_camera(self):
        if not self.isVisible():return
        if not self.release_camera():self.status.setText('Waiting for the previous camera to stop.');return
        self.worker=CaptureEnrollmentWorker(self.source.text(),user=getattr(self.parent(),'user',None));worker=self.worker
        worker.frame_ready.connect(lambda raw,preview,count,w=worker:self.show_preview(raw,preview,count) if self.worker is w else None,Qt.ConnectionType.QueuedConnection)
        worker.message.connect(lambda message,w=worker:self.status.setText(message) if self.worker is w else None,Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(lambda w=worker:self.preview_finished(w));worker.start()
    def mirror_changed(self,checked):
        try:settings.save_mirror_preview(checked)
        except OSError:self.status.setText('Preview changed, but the preference could not be saved.')
    def show_preview(self,raw,preview,count):
        self.latest=raw if count==1 else None;self.capture.setEnabled(self.latest is not None)
        self.status.setText('One face detected — ready to capture.' if count==1 else ('No face detected. Face the camera.' if count==0 else 'Multiple faces detected. Only the student being enrolled should be in frame.'))
        preview=preview_frame(preview,self.mirror.isChecked());rgb=cv2.cvtColor(preview,cv2.COLOR_BGR2RGB);h,w=rgb.shape[:2];img=QImage(rgb.data,w,h,rgb.strides[0],QImage.Format.Format_RGB888).copy()
        self.preview.setPixmap(QPixmap.fromImage(img).scaled(self.preview.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
    def preview_finished(self,worker):
        if self.worker is worker:self.latest=None;self.capture.setEnabled(False)
    @safe
    def capture_face(self):
        if self.latest is None:raise ValueError('A single clear face is required.')
        ok,raw=cv2.imencode('.png',self.latest)
        if not ok:raise ValueError('Could not encode the captured photo.')
        self.capture_bytes=raw.tobytes();self.accept()
    def release_camera(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.running=False;self.worker.cancel_event.set();return False
        self.latest=None
        if hasattr(self,'capture'):self.capture.setEnabled(False)
        return True
    def done(self,result):
        if not self.release_camera():self.status.setText('Stopping camera safely…');QTimer.singleShot(100,lambda:self.done(result));return
        super().done(result)
    def closeEvent(self,event):
        if not self.release_camera():self.status.setText('Stopping camera safely…');event.ignore();QTimer.singleShot(100,self.close);return
        super().closeEvent(event)

class StudentForm(QDialog):
    def __init__(self,parent,student=None):
        super().__init__(parent);self.student=student
        outer,body=dialog_shell(self,'Edit Student' if student else 'Add Student','Enter the student’s academic and contact details.')
        self.roll=field('e.g. 2024-SE-001');self.name=field('Enter full name');self.email=field('student@example.com');self.phone=field('Phone number (optional)')
        self.dept=QComboBox();load_combo(self.dept,db.departments(),lambda r:r['dept_name'],'dept_id')
        self.sem=QSpinBox();self.sem.setRange(1,8);self.year=QSpinBox();self.year.setRange(1990,date.today().year+1);self.year.setValue(date.today().year)
        grid=QGridLayout();grid.setHorizontalSpacing(16);grid.setVerticalSpacing(14)
        for i,(label,w) in enumerate([('Roll number *',self.roll),('Full name *',self.name),('Email address',self.email),('Phone number',self.phone),('Department',self.dept),('Semester',self.sem),('Batch year',self.year)]):grid.addWidget(form_cell(label,w),i//2,i%2)
        body.addLayout(grid);body.addWidget(text_hint('* Required fields'))
        if student:
            full=db.one('SELECT * FROM students WHERE student_id=:id',{'id':student['student_id']});self.roll.setText(full['roll_number']);self.roll.setReadOnly(True);self.name.setText(full['full_name']);self.email.setText(full['email'] or '');self.phone.setText(full['phone'] or '')
            self.dept.setCurrentIndex(self.dept.findData(full['dept_id']));self.sem.setValue(full['semester']);self.year.setValue(full['batch_year'])
        footer=QHBoxLayout();footer.addStretch();footer.addWidget(action('Cancel',self.reject));footer.addWidget(button('Save changes' if student else 'Add student',self.save));outer.addLayout(footer)
    @safe
    def save(self):
        args=(self.name.text(),self.email.text(),self.phone.text(),self.dept.currentData(),self.sem.value(),self.year.value())
        if self.student:db.update_student(self.student['student_id'],*args)
        else:db.add_student(self.name.text(),self.roll.text(),self.email.text(),self.phone.text(),self.dept.currentData(),self.sem.value(),self.year.value())
        self.accept()

class StudentLoginDialog(QDialog):
    def __init__(self,parent):
        super().__init__(parent);outer,body=dialog_shell(self,'Create Student Login','Assign login credentials to an existing student.',600)
        self.student=QComboBox();load_combo(self.student,db.students(),student_label,'student_id');self.email=field('student@example.com');self.password=field('Minimum 8 characters',password=True)
        for label,w in [('Student',self.student),('Email / username',self.email),('Password',self.password)]:body.addWidget(form_cell(label,w))
        h=QHBoxLayout();h.addStretch();h.addWidget(action('Cancel',self.reject));h.addWidget(button('Create login',self.save));outer.addLayout(h)
    @safe
    def save(self):
        if not self.student.currentData():raise ValueError('Select a student.')
        db.create_student_login(self.student.currentData(),self.email.text(),self.password.text());alert(self,'Student login created.');self.accept()

class TeacherEditDialog(QDialog):
    def __init__(self,parent,teacher):
        super().__init__(parent);self.teacher=teacher;outer,body=dialog_shell(self,'Edit Teacher','Update the teacher’s profile details.',600)
        details=db.one('SELECT full_name,department FROM users WHERE user_id=:id',{'id':teacher['user_id']})
        self.name=field('Full name');self.name.setText(details['full_name']);self.dept=QComboBox();load_combo(self.dept,db.departments(),lambda r:r['dept_name'],'dept_id')
        idx=self.dept.findText(details['department'] or '')
        if idx>=0:self.dept.setCurrentIndex(idx)
        body.addWidget(form_cell('Full name',self.name));body.addWidget(form_cell('Department',self.dept))
        h=QHBoxLayout();h.addStretch();h.addWidget(action('Cancel',self.reject));h.addWidget(button('Save changes',self.save));outer.addLayout(h)
    @safe
    def save(self):
        db.update_teacher(self.teacher['user_id'],self.name.text(),self.dept.currentText());self.accept()

class BatchEnrollment(QDialog):
    def __init__(self,parent):
        super().__init__(parent);self.setWindowTitle('Batch Face Enrollment');self.resize(880,600);self.students=db.students();self.entries=[];self.worker=None
        outer=QVBoxLayout(self);outer.setContentsMargins(26,24,26,24);outer.setSpacing(14)
        title=QLabel('Batch Face Enrollment');title.setObjectName('dialogTitle');outer.addWidget(title);outer.addWidget(text_hint('Choose one clear, individual face photo for each student. Review the result for every photo.'))
        box,body=section('Add photos','Select a student, choose their photo, then repeat for the rest of the batch.')
        h=QHBoxLayout();self.student=QComboBox();load_combo(self.student,self.students,student_label,'student_id');h.addWidget(self.student,1);self.add_photo_button=button('+ Add photo',self.add_photo);h.addWidget(self.add_photo_button);body.addLayout(h);outer.addWidget(box)
        self.tab=table(['Student','Photo','Result']);outer.addWidget(self.tab,1)
        self.consent=QCheckBox('I have obtained informed, voluntary biometric consent from every listed student.');outer.addWidget(self.consent)
        outer.addWidget(text_hint('Manual attendance remains available. Photos are processed in memory; new encrypted face templates are stored locally for this Windows user.'))
        footer=QHBoxLayout();footer.addStretch();self.close_button=action('Close',self.reject);footer.addWidget(self.close_button);self.enroll_button=action('Enroll batch',self.run_batch,'success');footer.addWidget(self.enroll_button);outer.addLayout(footer)
    @safe
    def add_photo(self):
        sid=self.student.currentData()
        if not sid:raise ValueError('Select a student.')
        if any(e[0]==sid for e in self.entries):raise ValueError('Student is already in this batch.')
        p,_=QFileDialog.getOpenFileName(self,'Select face photo','','Images (*.png *.jpg *.jpeg *.bmp)')
        if p:
            self.entries.append((sid,self.student.currentText(),p));self.tab.setRowCount(len(self.entries));r=len(self.entries)-1
            for col,val in enumerate([self.student.currentText(),p,'Waiting']):self.tab.setItem(r,col,QTableWidgetItem(val))
    @safe
    def run_batch(self):
        if not self.entries:raise ValueError('Add at least one photo.')
        if not self.consent.isChecked():raise ValueError('Confirm informed consent for every listed student before enrolling.')
        if self.worker and self.worker.isRunning():return
        self.student.setEnabled(False);self.add_photo_button.setEnabled(False);self.enroll_button.setEnabled(False);self.close_button.setText('Cancel remaining')
        from .privacy import record_consent
        entries=list(self.entries);user=getattr(self.parent(),'user',None)
        def consent_all():
            for sid,_,_ in entries:record_consent(user,sid,True)
        task=BackgroundTask(consent_all);self.consent_task=task
        def start(_):
            self.consent_task=None;self.worker=BatchEnrollmentWorker(entries,self);self.worker.progress.connect(self.batch_progress,Qt.ConnectionType.QueuedConnection);self.worker.completed.connect(self.batch_completed,Qt.ConnectionType.QueuedConnection);self.worker.start()
        def failed(exc):self.consent_task=None;self.batch_completed(0,0,False);error(self,exc)
        task.signals.succeeded.connect(start,Qt.ConnectionType.QueuedConnection);task.signals.failed.connect(failed,Qt.ConnectionType.QueuedConnection);QThreadPool.globalInstance().start(task)
    def batch_progress(self,index,status):
        self.tab.setItem(index,2,QTableWidgetItem(status))
    def batch_completed(self,success,processed,cancelled):
        self.student.setEnabled(True);self.add_photo_button.setEnabled(True);self.enroll_button.setEnabled(True);self.close_button.setEnabled(True);self.close_button.setText('Close')
        result='cancelled' if cancelled else 'finished';alert(self,f'Enrollment {result}: {success} of {len(self.entries)} photo(s) successful ({processed} processed). Check each row for errors.')
    def reject(self):
        if getattr(self,'consent_task',None) is not None:return
        if self.worker and self.worker.isRunning():self.worker.cancel();self.close_button.setEnabled(False);return
        super().reject()
    def closeEvent(self,event):
        if getattr(self,'consent_task',None) is not None:event.ignore();return
        if self.worker and self.worker.isRunning():self.worker.cancel();event.ignore();return
        super().closeEvent(event)

from .ui_reads import install as _install_background_reads
_install_background_reads(MainWindow)

def finish_application(app):
    from PySide6.QtCore import QCoreApplication
    import shiboken6
    if not QThreadPool.globalInstance().waitForDone(30000):raise RuntimeError('Background operations did not finish during shutdown.')
    for widget in app.topLevelWidgets():widget.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    shiboken6.delete(app)

def main():
    app=QApplication(sys.argv);app.setStyleSheet(STYLE)
    from .diagnostics import install_exception_hook
    install_exception_hook()
    from . import configuration
    try:configured=configuration.load_runtime()
    except (ValueError,OSError):configured=False
    if not configured:
        from .configuration_ui import DatabaseSetup
        if DatabaseSetup().exec()!=QDialog.DialogCode.Accepted:finish_application(app);return 0
    w=Login();w.show()
    if '--smoke-test' in sys.argv:QTimer.singleShot(1500,app.quit)
    code=app.exec();finish_application(app);return code


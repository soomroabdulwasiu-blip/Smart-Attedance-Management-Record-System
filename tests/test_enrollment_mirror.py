import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import cv2,numpy as np
from PySide6.QtWidgets import QApplication,QDialog
from amrs import gui,settings

def test_enrollment_mirror_changes_preview_only(monkeypatch,tmp_path):
    monkeypatch.setattr(settings,'SETTINGS_PATH',tmp_path/'ui_settings.json')
    app=QApplication.instance() or QApplication([])
    d=gui.CameraCaptureDialog(None,'Test')
    raw=np.zeros((20,30,3),dtype=np.uint8);raw[3,2]=[10,50,200];original=raw.copy();orientations=[]
    original_preview=gui.preview_frame
    def spy(frame,mirror):orientations.append(mirror);return original_preview(frame,mirror)
    monkeypatch.setattr(gui,'preview_frame',spy)
    d.show_preview(raw,raw.copy(),1);assert d.mirror.isChecked() and orientations[-1] is True
    d.mirror.setChecked(False);d.show_preview(raw,raw.copy(),1);assert orientations[-1] is False
    d.mirror.setChecked(True);d.show_preview(raw,raw.copy(),1);d.capture_face()
    saved=cv2.imdecode(np.frombuffer(d.capture_bytes,dtype=np.uint8),cv2.IMREAD_COLOR)
    assert d.result()==QDialog.DialogCode.Accepted and np.array_equal(saved,original) and np.array_equal(raw,original)

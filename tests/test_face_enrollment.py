import cv2
import numpy as np
import pytest
from amrs import face

def test_unenrolled_references_are_never_loaded(tmp_path,monkeypatch):
    monkeypatch.setattr(face,'FACE_DIR',tmp_path)
    monkeypatch.setattr(face,'LEGACY_FACE_DIR',tmp_path)
    (tmp_path/'student.image').write_bytes(b'existing-but-not-enrolled')
    engine=face.FaceEngine.__new__(face.FaceEngine)
    monkeypatch.setattr(engine,'reference',lambda path: pytest.fail('Unenrolled face must not be loaded'))
    refs,skipped=engine.load_references([{'student_id':'student','roll_number':'R1','face_enrolled':0}])
    assert refs==[] and skipped==[]

def test_failed_database_update_restores_previous_reference(tmp_path,monkeypatch):
    monkeypatch.setattr(face,'FACE_DIR',tmp_path)
    target=tmp_path/'student.image';target.write_bytes(b'old-reference')
    engine=face.FaceEngine.__new__(face.FaceEngine)
    monkeypatch.setattr(engine,'detect',lambda image:[np.zeros(15,dtype=np.float32)])
    monkeypatch.setattr(engine,'encode',lambda image,detection:np.ones(128))
    monkeypatch.setattr(face.privacy,'has_consent',lambda sid:True)
    monkeypatch.setattr(face.db,'set_face_enrolled',lambda sid: (_ for _ in ()).throw(RuntimeError('Database unavailable')))
    ok,raw=cv2.imencode('.png',np.zeros((50,50,3),dtype=np.uint8));assert ok
    with pytest.raises(RuntimeError):engine.save_reference_bytes('student',raw.tobytes())
    assert target.read_bytes()==b'old-reference'
    assert not (tmp_path/'student.tmp').exists()
    assert not (tmp_path/'student.template').exists()

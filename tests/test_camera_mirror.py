import numpy as np
from amrs.face import preview_frame,preview_box

def test_mirror_preview_does_not_change_saved_frame():
    raw=np.zeros((2,6,3),dtype=np.uint8);raw[:,0]=[10,20,30];before=raw.copy()
    mirrored=preview_frame(raw,True)
    assert np.array_equal(raw,before)
    assert np.array_equal(mirrored[:,-1],raw[:,0])
    assert np.array_equal(preview_frame(raw,False),raw)

def test_face_box_moves_with_mirrored_preview():
    assert preview_box(10,5,20,12,100,False)==(10,5,20,12)
    assert preview_box(10,5,20,12,100,True)==(70,5,20,12)

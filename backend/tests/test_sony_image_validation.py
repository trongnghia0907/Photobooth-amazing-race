"""Validation-only regressions. No camera, operator storage or real photo fixtures."""
from io import BytesIO
import hashlib
import struct
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from PIL import Image
from app.config import Settings
from app.services.images import is_jpeg_image, validate_image
from app.services.camera.base import CameraError, CapturedPhoto
from app.services.camera.sony_ptp import check_jpeg, object_info
from app.services.camera.sony_wia import MAX_TRANSFER
from app.services.camera.sony_zve10 import SonyZvE10CameraAdapter
from test_sony_mpo import mpo
from test_sony_ptp import jpeg, object_dataset


def adapter_photo(data):
    photo=CapturedPhoto(data,'image/jpeg','camera_original')
    driver=SimpleNamespace(
        get_status=lambda:{'connected':True,'previewing':False,'model':'ZV-E10'},
        get_captured_photo=lambda _reference,_deadline:photo)
    adapter=SonyZvE10CameraAdapter(driver);adapter.connected=True
    return adapter,photo


@pytest.mark.parametrize('kind',['JPEG','MPO'])
def test_original_survives_all_validators_without_recompression(tmp_path,kind):
    data=jpeg('blue') if kind=='JPEG' else mpo()
    original_hash=hashlib.sha256(data).hexdigest()
    with Image.open(BytesIO(data)) as image:
        assert image.format==kind and is_jpeg_image(image)
        assert image.size==(320,240)
    assert check_jpeg(data)==(320,240)
    adapter,original=adapter_photo(data)
    returned=adapter.get_captured_photo('validation-only',time.monotonic()+5)
    assert returned is original and returned.data is data
    normalized=validate_image(returned.data,'image/jpeg',Settings(tmp_path))
    assert hashlib.sha256(data).hexdigest()==original_hash==normalized.input_hash
    fast=validate_image(returned.data,'image/jpeg',Settings(tmp_path),png_compress_level=5)
    assert fast.input_hash==original_hash
    with Image.open(BytesIO(normalized.data)) as standard, Image.open(BytesIO(fast.data)) as quicker:
        assert (quicker.mode,quicker.size,quicker.tobytes())==(standard.mode,standard.size,standard.tobytes())
    with Image.open(BytesIO(normalized.data)) as working:
        assert working.format=='PNG'
        # Regular fixture has EXIF orientation 6; MPO primary has no rotation.
        assert working.size==((240,320) if kind=='JPEG' else (320,240))
        pixel=working.getpixel((10,10))
        assert pixel[2]>200 and pixel[0]<30  # Primary blue, never red MPO thumbnail.


def invalid_payload(kind):
    if kind=='empty':return b''
    if kind=='garbage':return b'not a camera JPEG'
    if kind=='jpeg_header_only':return jpeg('blue')[:100]
    if kind=='jpeg_truncated_scan':
        data=jpeg('blue');return data[:data.index(b'\xff\xda')+16]
    if kind=='mpo_truncated_primary':return mpo()[:len(mpo())//4]
    output=BytesIO();Image.new('RGB',(32,24),'blue').save(output,format=kind)
    return output.getvalue()


@pytest.mark.parametrize('kind',['empty','garbage','jpeg_header_only','jpeg_truncated_scan','mpo_truncated_primary','PNG','GIF','BMP'])
def test_invalid_or_non_jpeg_original_is_rejected_at_every_boundary(tmp_path,kind):
    data=invalid_payload(kind)
    with pytest.raises(CameraError):check_jpeg(data)
    adapter,_=adapter_photo(data)
    with pytest.raises(CameraError):adapter.get_captured_photo('validation-only',time.monotonic()+5)
    with pytest.raises(HTTPException) as caught:validate_image(data,'image/jpeg',Settings(tmp_path))
    assert caught.value.status_code==(413 if not data else 422)


@pytest.mark.parametrize('kind',['JPEG','MPO'])
def test_declared_mime_and_configured_byte_pixel_limits_remain_enforced(tmp_path,kind):
    data=jpeg('blue') if kind=='JPEG' else mpo()
    exact=Settings(tmp_path,max_upload_bytes=len(data),max_image_pixels=320*240)
    assert validate_image(data,'image/jpeg',exact).input_hash==hashlib.sha256(data).hexdigest()
    for settings in [Settings(tmp_path,max_upload_bytes=len(data)-1),
                     Settings(tmp_path,max_image_pixels=320*240-1)]:
        with pytest.raises(HTTPException) as caught:validate_image(data,'image/jpeg',settings)
        assert caught.value.status_code==413
    for mime,expected in [('image/png',422),('image/webp',422),('image/gif',415)]:
        with pytest.raises(HTTPException) as caught:validate_image(data,mime,Settings(tmp_path))
        assert caught.value.status_code==expected


@pytest.mark.parametrize('size,allowed',[(0,False),(MAX_TRANSFER,True),(MAX_TRANSFER+1,False)])
def test_ptp_object_size_boundary_is_checked_before_allocating_payload(size,allowed):
    raw=bytearray(object_dataset(jpeg('blue')))
    struct.pack_into('<I',raw,8,size)
    if allowed:assert object_info(bytes(raw))['size']==size
    else:
        with pytest.raises(CameraError):object_info(bytes(raw))

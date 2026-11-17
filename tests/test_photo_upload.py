from io import BytesIO
from pathlib import Path
import importlib.util
import unittest
from PIL import Image

spec=importlib.util.spec_from_file_location('board_upload',Path(__file__).resolve().parents[1]/'photo-upload/server.py')
upload=importlib.util.module_from_spec(spec)
spec.loader.exec_module(upload)


class PhotoUploadTests(unittest.TestCase):
    def test_multiple_photos(self):
        stream=BytesIO();Image.new('RGB',(2,2),'white').save(stream,format='PNG')
        image=stream.getvalue()
        def part(name):
            return b'--test-boundary\r\nContent-Disposition: form-data; name="photos"; filename="'+name+b'"\r\nContent-Type: image/png\r\n\r\n'+image+b'\r\n'
        body=part(b'front.png')+part(b'../../back.png')+b'--test-boundary--\r\n'
        files=upload.parse_upload('multipart/form-data; boundary=test-boundary',body)
        self.assertEqual(files,[('.png',image),('.png',image)])

    def test_nonimage_rejected(self):
        with self.assertRaises(ValueError):upload.image_extension(b'not an image')

    def test_empty_selection_rejected(self):
        with self.assertRaises(ValueError):upload.parse_upload('multipart/form-data; boundary=test',b'--test--\r\n')

    def test_phone_containers(self):
        for brand,extension in [(b'heic','.heic'),(b'mif1','.heic'),(b'avif','.avif')]:
            self.assertEqual(upload.image_extension(b'\x00\x00\x00\x18ftyp'+brand+b'\x00'*12),extension)

    def test_tiff(self):
        stream=BytesIO();Image.new('RGB',(2,2),'white').save(stream,format='TIFF')
        self.assertEqual(upload.image_extension(stream.getvalue()),'.tiff')

    def test_larger_than_previous_limit(self):
        stream=BytesIO();Image.new('RGB',(2,2),'white').save(stream,format='JPEG')
        payload=stream.getvalue()+b'\x00'*(21*1024*1024)
        body=(b'--large\r\nContent-Disposition: form-data; name="photos"; filename="large.jpg"\r\n\r\n'+payload+b'\r\n--large--\r\n')
        form,files=upload.parse_stream('multipart/form-data; boundary=large',BytesIO(body),len(body))
        self.assertEqual(files[0][0],'.jpg')
        self.assertEqual(files[0][1].seek(0,2),len(payload))

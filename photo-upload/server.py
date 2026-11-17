"""Temporary LAN-only multi-photo receiver for TellStick recovery inspection."""
from http.server import HTTPServer, BaseHTTPRequestHandler
import cgi
import shutil
import re
from urllib.parse import urlsplit
from pathlib import Path
from io import BytesIO
import html
import json
import os
import secrets
import sys
import uuid
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
DIRECTORY=ROOT/'secrets/recovery/board-photos'
MAX_TOTAL=1024*1024*1024
MAX_FILE=256*1024*1024


def image_extension_stream(stream):
    stream.seek(0)
    header=stream.read(128)
    stream.seek(0)
    # ISO base media containers: include compatible brands used by phone cameras.
    if header[4:8]==b'ftyp':
        brands=[header[8:12]]+[header[i:i+4] for i in range(16,len(header)-3,4)]
        if any(b in (b'avif',b'avis') for b in brands):return '.avif'
        if any(b in (b'heic',b'heix',b'hevc',b'hevx',b'mif1',b'msf1') for b in brands):return '.heic'
    try:
        with Image.open(stream) as im:
            kind=im.format
            im.verify()
        return {'JPEG':'.jpg','MPO':'.jpg','PNG':'.png','WEBP':'.webp',
                'GIF':'.gif','TIFF':'.tiff','BMP':'.bmp','JPEG2000':'.jp2',
                'AVIF':'.avif'}[kind]
    except (OSError,ValueError,KeyError):
        raise ValueError('Unsupported image. Choose JPEG, PNG, HEIC, HEIF, AVIF, TIFF/DNG, WebP or GIF.') from None
    finally:
        stream.seek(0)


def image_extension(data):
    return image_extension_stream(BytesIO(data))


def parse_stream(content_type,stream,size):
    if not content_type.startswith('multipart/form-data;'):
        raise ValueError('Expected photo upload form')
    form=cgi.FieldStorage(fp=stream,environ={'REQUEST_METHOD':'POST',
        'CONTENT_TYPE':content_type,'CONTENT_LENGTH':str(size)},
        limit=size,max_num_fields=25)
    files=[]
    for part in form.list or []:
        if part.name!='photos' or not part.filename:continue
        part.file.seek(0,2)
        length=part.file.tell()
        if not 0<length<=MAX_FILE:raise ValueError('Each photo must be between 1 byte and 256 MiB.')
        if part.done==-1:raise ValueError('Upload interrupted; please retry.')
        part.file.seek(0)
        files.append((image_extension_stream(part.file),part.file))
        if len(files)>20:raise ValueError('Please upload at most 20 photos at a time.')
    if not files:raise ValueError('Please select at least one photo.')
    return form,files


def parse_upload(content_type,data):
    form,files=parse_stream(content_type,BytesIO(data),len(data))
    return [(ext,stream.read()) for ext,stream in files]


def page(message=''):
    return ('''<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1"><meta charset="utf-8">
<title>TellStick board photos</title><style>body{font:18px system-ui;background:#f3f5f7;color:#17212b;margin:0;padding:24px}main{max-width:560px;margin:30px auto;background:white;padding:28px;border-radius:16px}h1{font-size:28px}input,button{font:inherit;max-width:100%;margin:15px 0}button{background:#135f66;color:white;border:0;border-radius:8px;padding:14px 22px}p{line-height:1.5}.status{font-weight:bold;color:#135f66}</style>
<main><h1>TellStick board photos</h1><p>Select several photos from your phone, then tap Upload photos.</p><p>Include both board sides and close-ups of chip markings and programming pads. Keep the board disconnected from power and Ethernet.</p>'''+('<p class="status">'+html.escape(message)+'</p>' if message else '')+'''
<form method="post" enctype="multipart/form-data"><label for="photos">Board images</label><br><input id="photos" name="photos" type="file" accept="image/*,.heic,.heif,.avif,.dng,.tif,.tiff" multiple required><br><button type="submit">Upload photos</button></form><p>Photos are stored privately on Argus. Up to 20 photos per batch, 256 MiB each, 1 GiB total.</p></main>''').encode()


def main():
    os.umask(0o077)
    for p in (ROOT/'secrets',ROOT/'secrets/recovery',DIRECTORY):
        if p.is_symlink():raise ValueError('Unsafe photo directory')
        p.mkdir(mode=0o700,exist_ok=True)
        p.chmod(0o700)
    route='/'+secrets.token_urlsafe(24)
    session=DIRECTORY/'session.json'
    if session.exists():
        previous=urlsplit(json.loads(session.read_text()).get('url',''))
        if previous.netloc=='192.168.1.149:8767' and re.fullmatch(r'/[A-Za-z0-9_-]{24,}',previous.path):
            route=previous.path
    authority='192.168.1.149:8767'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,message=''):
            self.send_response(status)
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('Referrer-Policy','same-origin')
            self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(page(message))
        def valid(self):
            return self.path==route and self.headers.get('Host')==authority
        def do_GET(self):
            if not self.valid():self.send_error(404);return
            self.reply(200)
        def do_POST(self):
            if not self.valid() or self.headers.get('Origin') not in (None,'null','http://'+authority):
                self.send_error(403);return
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=MAX_TOTAL:raise ValueError('Batch exceeds 1 GiB. Please select fewer photos.')
                self.connection.settimeout(600)
                form,files=parse_stream(self.headers.get('Content-Type',''),self.rfile,size)
                for extension,payload in files:
                    path=DIRECTORY/(uuid.uuid4().hex+extension)
                    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                    try:
                        with os.fdopen(fd,'wb') as out:shutil.copyfileobj(payload,out,1024*1024)
                    except OSError:
                        path.unlink(missing_ok=True)
                        raise
                print('Received '+str(len(files))+' board photos.',flush=True)
                self.reply(200,str(len(files))+' photos uploaded successfully. You can select more or return to the chat.')
            except ValueError as exc:
                self.reply(400,str(exc) if str(exc).startswith(('Unsupported image.', 'Each photo', 'Batch exceeds', 'Please ', 'Upload interrupted', 'Expected photo')) else 'Invalid upload. Please select the photos again.')
            except OSError:
                self.reply(400,'Upload interrupted or storage unavailable. Please retry.')
    with HTTPServer(('192.168.1.149',8767),Handler) as server:
        url='http://'+authority+route
        # Library was downloaded earlier solely for deterministic QR generation.
        sys.path.insert(0,'/tmp/tellstick-qr-library')
        import qrcode
        qrcode.make(url).save('/tmp/tellstick-direct-upload-qr.png')
        session=DIRECTORY/'session.json'
        fd=os.open(session,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as out:json.dump({'url':url,'directory':str(DIRECTORY)},out)
        print('Local multi-photo upload server ready on Argus port 8767.',flush=True)
        server.serve_forever()


if __name__=='__main__':main()

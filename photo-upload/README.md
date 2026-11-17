# Local TellStick board photo upload

Temporary HTTP receiver on Argus 192.168.1.149:8767. The phone must be on the same
reachable home LAN. The capability URL is encoded in /tmp/tellstick-direct-upload-qr.png
and saved privately in secrets/recovery/board-photos/session.json. It is a direct
file-upload form, not the ChatGPT Page created earlier.

Run with `python3.12 photo-upload/server.py`. Requires Pillow and the qrcode library
previously downloaded under /tmp/tellstick-qr-library. Restarting preserves the private session URL. Do not start a second instance on the same port.

The form accepts multiple photos. Files are validated as supported images (HEIC
is recognized by its container signature), named randomly rather than using phone
filenames, and stored with mode 0600 under secrets/recovery/board-photos. Directories
use 0700 and secrets/ is excluded from Git. It does not serve uploaded files or
publish them online. HTTP is unencrypted over the LAN; use the trusted home Wi-Fi.

Limits: 20 photos per batch, 256 MiB per photo and 1 GiB request body. Request
logging is disabled. No TellStick device command is sent. Stop the server after
all images have been received and reviewed. The page response was verified from
Argus; phone-specific rendering/reachability remains dependent on the phone and
LAN. Tests cover multipart uploads with multiple images and invalid/empty input.

Multipart uploads stream to temporary files, then copy to private storage. JPEG, PNG,
HEIC/HEIF, AVIF, TIFF/DNG, WebP, GIF, BMP and JPEG2000 are accepted. Container
signatures identify HEIC/AVIF; full decoding requires additional codecs.

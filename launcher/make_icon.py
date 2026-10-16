"""Package the supplied Blood logo as a multiresolution Windows icon."""
from pathlib import Path
import os
import struct
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QPixmap
from bloodpsp_launcher.resources import resource

app = QApplication([])
source = QPixmap(str(resource("assets/blood-icon.png")))
if source.isNull():
    raise RuntimeError("Missing Blood icon artwork.")
images = []
for size in (16, 24, 32, 48, 64, 128, 256):
    pixmap = source.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not pixmap.save(buffer, "PNG"):
        raise RuntimeError("Could not encode icon.")
    images.append((size, bytes(data)))
offset = 6 + 16 * len(images)
directory = []
for size, data in images:
    directory.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
    offset += len(data)
Path(sys.argv[1]).write_bytes(struct.pack("<HHH", 0, 1, len(images)) + b"".join(directory) + b"".join(data for _, data in images))

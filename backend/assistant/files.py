"""Files the owner hands to the /chat/ agent: attachments sent with a chat message, and the "For the site" heading
on /upload/ (photos, videos, menus). They go to `CHAT_FILES_DIR`, outside `backend/media` so nothing is public
until the agent publishes it, and group `claude` (the directory is setgid, made by ansible) so the agent reads
them without sudo. The IDs and the ad card on /upload/ stay in `DROP_DIR`, which the agent's group cannot read.

    CHAT_FILES_DIR/upload/<stamp>-<n>__<name>         from /upload/
    CHAT_FILES_DIR/chat/<conversation>/<stamp>-<n>__<name>   attached in /chat/
"""
import os
import shutil
from datetime import datetime

from django.conf import settings
from django.core.files.move import file_move_safe
from django.utils.text import get_valid_filename

MB = 1024 * 1024
# Refuse rather than fill the disk the database lives on.
MIN_FREE_BYTES = 5 * 1024 * MB


def folder(*parts):
    path = os.path.join(settings.CHAT_FILES_DIR, *[str(p) for p in parts])
    os.makedirs(path, mode=0o2750, exist_ok=True)
    return path


def low_on_disk():
    try:
        return shutil.disk_usage(settings.CHAT_FILES_DIR).free < MIN_FREE_BYTES
    except FileNotFoundError:
        return shutil.disk_usage('/').free < MIN_FREE_BYTES


def store(uploads, *parts, note=''):
    """Save each upload (and an optional note) under CHAT_FILES_DIR/<parts>. Returns [(path, size)]."""
    path = folder(*parts)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    saved = []
    for n, upload in enumerate(uploads):
        name = get_valid_filename(os.path.basename(upload.name or 'file'))[-120:] or 'file'
        dest = os.path.join(path, f'{stamp}-{n}__{name}')
        if hasattr(upload, 'temporary_file_path'):
            # Same disk as the upload temp dir, so a 1 GB video is a rename, not a copy.
            file_move_safe(upload.temporary_file_path(), dest, allow_overwrite=False)
        else:
            with open(dest, 'xb') as out:
                for chunk in upload.chunks():
                    out.write(chunk)
        os.chmod(dest, 0o640)
        saved.append((dest, upload.size))
    if note:
        dest = os.path.join(path, f'{stamp}-note__note.txt')
        with open(dest, 'x', encoding='utf-8') as out:
            out.write(note + '\n')
        os.chmod(dest, 0o640)
        saved.append((dest, os.path.getsize(dest)))
    return saved


def store_paths(parts, *folder_parts, note=''):
    """`store` for files that are already on this disk (the pieces /upload/ assembled): [(path, original name)]."""
    path = folder(*folder_parts)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    saved = []
    for n, (src, original) in enumerate(parts):
        name = get_valid_filename(os.path.basename(original or 'file'))[-120:] or 'file'
        dest = os.path.join(path, f'{stamp}-{n}__{name}')
        file_move_safe(src, dest, allow_overwrite=False)
        os.chmod(dest, 0o640)
        saved.append((dest, os.path.getsize(dest)))
    if note:
        dest = os.path.join(path, f'{stamp}-note__note.txt')
        with open(dest, 'x', encoding='utf-8') as out:
            out.write(note + '\n')
        os.chmod(dest, 0o640)
        saved.append((dest, os.path.getsize(dest)))
    return saved


def size(n):
    return f'{n / MB:.1f} MB' if n >= MB / 10 else f'{max(1, round(n / 1024))} KB'


def describe(saved):
    """The lines appended to a chat prompt so the agent knows where the files are."""
    return '\n'.join(f'- {path} ({size(n)})' for path, n in saved)

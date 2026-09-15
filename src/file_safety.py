import os, stat, zipfile, json
from pathlib import Path, PurePosixPath
from src.config import settings
from src.auth import validate_metadata
EXTENSIONS={'.pdf','.png','.jpg','.jpeg','.tif','.tiff','.bmp','.webp','.txt','.md','.csv','.json','.xml','.html','.htm','.docx','.pptx','.xlsx','.odt','.ods','.odp'}
ZIP_EXTENSIONS={'.docx','.pptx','.xlsx','.odt','.ods','.odp'}

def read_regular(path, limit):
    flags=os.O_RDONLY | getattr(os,'O_NOFOLLOW',0)
    fd=os.open(path,flags)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size>limit: raise ValueError('Not a regular bounded file')
        with os.fdopen(fd,'rb',closefd=False) as f: data=f.read(limit+1)
        if len(data)>limit: raise ValueError('File exceeds limit')
        return data
    finally: os.close(fd)

def safe_path(name):
    if not isinstance(name,str) or not name or len(name)>180 or Path(name).name != name or name in {'.','..'}:
        raise ValueError('Only a direct-child filename is accepted')
    root=settings.documents
    if root.is_symlink() or not root.is_dir(): raise ValueError('Document root must be a real directory')
    path=root/name
    if path.is_symlink(): raise ValueError('Symlinks rejected')
    if path.suffix.lower() not in EXTENSIONS: raise ValueError('Unsupported extension')
    return path

def inspect_bytes(data,ext):
    signatures={'.pdf':b'%PDF-', '.png':b'\x89PNG\r\n\x1a\n','.jpg':b'\xff\xd8\xff','.jpeg':b'\xff\xd8\xff',
                '.bmp':b'BM','.webp':b'RIFF'}
    if ext in signatures and not data.startswith(signatures[ext]): raise ValueError('Extension/signature mismatch')
    if ext=='.webp' and data[8:12]!=b'WEBP': raise ValueError('Invalid WEBP')
    if ext in {'.tif','.tiff'} and data[:4] not in {b'II*\x00',b'MM\x00*'}: raise ValueError('Invalid TIFF')
    if ext in ZIP_EXTENSIONS:
        import io
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos=z.infolist()
            if len(infos)>5000: raise ValueError('Archive entry limit')
            total=0
            for item in infos:
                p=PurePosixPath(item.filename)
                if p.is_absolute() or '..' in p.parts or '\\' in item.filename or ':' in item.filename:
                    raise ValueError('Unsafe archive path')
                if (item.external_attr>>16)&0o170000 == 0o120000: raise ValueError('Archive symlink rejected')
                if item.flag_bits & 1: raise ValueError('Encrypted archive rejected')
                total+=item.file_size
                if total>100_000_000 or item.file_size/max(item.compress_size,1)>200:
                    raise ValueError('Archive expansion limit')
    return data

def snapshot(name):
    path=safe_path(name)
    data=inspect_bytes(read_regular(path,settings.max_file_bytes),path.suffix.lower())
    meta_path=path.with_name(path.name+'.meta.json')
    if meta_path.is_symlink(): raise ValueError('Metadata symlink rejected')
    meta=validate_metadata(json.loads(read_regular(meta_path,16384)))
    return path,data,meta

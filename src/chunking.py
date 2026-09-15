from src.config import settings

def chunk_text(text, size=None, overlap=None):
    size = size or settings.chunk_size
    overlap = settings.overlap if overlap is None else overlap
    if not 0 <= overlap < size: raise ValueError('Invalid overlap')
    text=text.strip(); out=[]; start=0
    while start < len(text):
        end=min(start+size,len(text))
        if end < len(text):
            boundary=text.rfind(' ', start+size//2,end)
            if boundary > start: end=boundary
        chunk=text[start:end].strip()
        if chunk: out.append(chunk)
        if end == len(text): break
        start=max(start+1,end-overlap)
    return out

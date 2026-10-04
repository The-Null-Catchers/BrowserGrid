def bounded_lines(chunks, limit=16000):
    """Reassemble Docker stream fragments without allowing an unbounded stdout line."""
    buffer = b""
    for chunk in chunks:
        for offset in range(0, len(chunk), limit):
            buffer += chunk[offset : offset + limit]
            while b"\n" in buffer or len(buffer) >= limit:
                newline = buffer.find(b"\n")
                end = newline + 1 if 0 <= newline < limit else limit
                yield buffer[:end].decode(errors="replace")
                buffer = buffer[end:]
    if buffer:
        yield buffer.decode(errors="replace")

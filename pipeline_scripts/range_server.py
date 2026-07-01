#!/usr/bin/env python3
"""HTTP-Server mit Range-Request-Unterstützung für PMTiles."""
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler


class RangeRequestHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()
        try:
            f = open(path, 'rb')
        except OSError:
            self.send_error(404)
            return None

        size = os.fstat(f.fileno())[6]
        range_header = self.headers.get('Range')

        if range_header:
            try:
                start_s, end_s = range_header.replace('bytes=', '').split('-')
                start = int(start_s)
                end = int(end_s) if end_s else size - 1
                length = end - start + 1
                self.send_response(206)
                self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
                self.send_header('Content-Length', length)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Accept-Ranges', 'bytes')
                self.end_headers()
                f.seek(start)
                return f
            except Exception:
                self.send_error(400, 'Bad Range header')
                f.close()
                return None
        else:
            self.send_response(200)
            self.send_header('Content-Length', size)
            self.send_header('Content-Type', self.guess_type(path))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Accept-Ranges', 'bytes')
            self.end_headers()
            return f

    def log_message(self, fmt, *args):
        # Nur Range-Requests und Fehler loggen, keine Tile-Spam
        if args and (str(args[1]) not in ('200', '206') or 'pmtiles' in str(args[0])):
            super().log_message(fmt, *args)


if __name__ == '__main__':
    port = 8080
    print(f'Range-Request-Server läuft auf http://localhost:{port}/')
    print(f'Öffne: http://localhost:{port}/stanford_test.html')
    HTTPServer(('', port), RangeRequestHandler).serve_forever()

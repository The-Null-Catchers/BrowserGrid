import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch

from cli.main import main


class CliRedirectTests(unittest.TestCase):
    def test_redirects_do_not_forward_api_key_or_replay_commands(self):
        received = []
        source_calls = []

        class Target(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append((self.command, self.headers.get("Authorization")))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")

            do_POST = do_GET

            def log_message(self, *args):
                pass

        target = ThreadingHTTPServer(("127.0.0.1", 0), Target)

        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self):
                source_calls.append(self.command)
                self.send_response(int(self.path.split("/")[1]))
                self.send_header("Location", f"http://127.0.0.1:{target.server_port}/target")
                self.end_headers()

            do_POST = do_GET

            def log_message(self, *args):
                pass

        source = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
        threads = [Thread(target=s.serve_forever, daemon=True) for s in (source, target)]
        for thread in threads:
            thread.start()

        def invoke(url, command):
            argv = ["browsergrid", "--url", url, "--token", "private-test-key", *command]
            with patch("sys.argv", argv):
                main()

        try:
            for command in (["projects", "workspace"], ["cancel", "run"]):
                for status in (301, 302, 303, 307, 308):
                    with self.subTest(command=command, status=status):
                        output, error = io.StringIO(), io.StringIO()
                        with redirect_stdout(output), redirect_stderr(error):
                            with self.assertRaises(SystemExit) as raised:
                                invoke(f"http://127.0.0.1:{source.server_port}/{status}", command)
                        self.assertEqual(raised.exception.code, 2)
                        self.assertIn(f"HTTP {status}", error.getvalue())
                        self.assertNotIn("private-test-key", error.getvalue())
            self.assertEqual(received, [])
            self.assertEqual(len(source_calls), 10)
            for command in (["projects", "workspace"], ["cancel", "run"]):
                with redirect_stdout(io.StringIO()) as output:
                    invoke(f"http://127.0.0.1:{target.server_port}", command)
                self.assertEqual(json.loads(output.getvalue()), {})
            self.assertEqual(
                received, [("GET", "Bearer private-test-key"), ("POST", "Bearer private-test-key")]
            )
        finally:
            for server in (source, target):
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join()

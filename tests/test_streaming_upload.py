import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server


class StreamingUploadTests(unittest.TestCase):
    def test_multipart_file_is_staged_exactly_and_request_spool_is_removed(self):
        boundary = "seed-boundary-123"
        payload = (b"conversation-data-" * 200000) + b"final-byte"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"archive.json\"\r\n"
            "Content-Type: application/json\r\n\r\n"
        ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
        with tempfile.TemporaryDirectory() as directory, patch.object(server, "UPLOAD_JOBS_DIR", Path(directory)):
            filename, staged = server.stream_multipart_upload(
                io.BytesIO(body), len(body), f"multipart/form-data; boundary={boundary}"
            )
            self.assertEqual(filename, "archive.json")
            self.assertEqual(staged.read_bytes(), payload)
            self.assertEqual(list(Path(directory).glob("request-*")), [])
            staged.unlink()

    def test_truncated_upload_is_rejected_and_spool_is_removed(self):
        boundary = "seed-boundary-456"
        body = f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"x.txt\"\r\n\r\nshort".encode()
        with tempfile.TemporaryDirectory() as directory, patch.object(server, "UPLOAD_JOBS_DIR", Path(directory)):
            with self.assertRaises(ValueError):
                server.stream_multipart_upload(io.BytesIO(body), len(body) + 50, f"multipart/form-data; boundary={boundary}")
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()

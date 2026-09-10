import functools
import json
import http.server
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone

import numpy as np
import zarr
from pynwb import NWBFile, NWBHDF5IO, TimeSeries

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inspect_reference import run, sample_selection, validate_config


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    requests = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.requests.append((self.path, self.headers.get('Range')))
        path = Path(self.translate_path(self.path))
        byte_range = self.headers.get('Range')
        if byte_range and path.is_file():
            start, end = byte_range.removeprefix('bytes=').split('-')
            size = path.stat().st_size
            start, end = int(start), min(int(end) if end else size - 1, size - 1)
            self.send_response(206)
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.send_header('Content-Length', str(end - start + 1))
            self.end_headers()
            with path.open('rb') as stream:
                stream.seek(start)
                self.wfile.write(stream.read(end - start + 1))
        else:
            super().do_GET()


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = Path.cwd()
        os.chdir(self.temp.name)

    def tearDown(self):
        os.chdir(self.old)
        self.temp.cleanup()

    def make_nwb(self):
        nwb = NWBFile('fixture', 'fixture', datetime.now(timezone.utc))
        nwb.add_acquisition(TimeSeries(name='signal', data=np.arange(400000).reshape(200000, 2),
                                       unit='volts', rate=1000.0))
        with NWBHDF5IO('data.nwb', 'w') as io:
            io.write(nwb)

    def make_zarr(self, version):
        root = zarr.open_group('image.ome.zarr', mode='w', zarr_format=version)
        meta = {'multiscales': [{'axes': [{'name': 'y', 'type': 'space'}, {'name': 'x', 'type': 'space'}],
                                'datasets': [{'path': '0'}]}]}
        root.attrs.update({'ome': {'version': '0.5', **meta}} if version == 3 else meta)
        root.create_array('0', data=np.arange(1024).reshape(32, 32), chunks=(8, 8))

    def server(self):
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0),
            functools.partial(RangeHandler, directory=self.temp.name))
        RangeHandler.requests = []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f'http://127.0.0.1:{server.server_port}'

    def test_nwb_local(self):
        self.make_nwb()
        report = run({'kind': 'nwb', 'input': 'data.nwb'})
        self.assertEqual(report['sample_elements'], 64)
        self.assertTrue(Path('report/report.json').is_file())
        self.assertEqual(Path('report/report.json').read_text(), Path('report/html/report.json').read_text())
        self.assertIn('html/report.json', Path('report/index.html').read_text())
        self.assertEqual(json.loads(Path('product.json').read_text())['brainlife'][0]['type'], 'success')

    def test_nwb_http_range_reads(self):
        self.make_nwb()
        report = run({'kind': 'nwb', 'input': self.server() + '/data.nwb?secret=redacted'})
        self.assertEqual(report['sample_elements'], 64)
        self.assertTrue(RangeHandler.requests)
        self.assertTrue(all(byte_range for _, byte_range in RangeHandler.requests))
        self.assertNotIn('secret', Path('report/report.json').read_text())

    def test_zarr_v2_and_v3(self):
        for version in (2, 3):
            with self.subTest(version=version):
                self.make_zarr(version)
                report = run({'kind': 'ome-zarr', 'input': 'image.ome.zarr'})
                self.assertEqual(report['sample_elements'], 64)
                self.assertEqual(report['sample_max'], 993)

    def test_zarr_http_reads_only_selected_chunks(self):
        self.make_zarr(3)
        report = run({'kind': 'ome-zarr', 'input': self.server() + '/image.ome.zarr'})
        self.assertEqual(report['sample_elements'], 64)
        chunks = [path for path, _ in RangeHandler.requests if '/c/' in path]
        self.assertEqual(len(chunks), 4)
        self.assertTrue(all(path.endswith('/0') for path in chunks))

    def test_invalid_inputs(self):
        for value in (0, -1, 4097, True, 1.5):
            with self.assertRaises(ValueError):
                validate_config({'kind': 'nwb', 'input': 'a.nwb', 'sample_elements': value})
        with self.assertRaises(ValueError):
            validate_config({'kind': 'bad', 'input': 'x'})

    def test_multidimensional_sample_budget(self):
        for shape in ((4, 5, 20, 30, 40), (0, 5), (), (1000000,)):
            data = np.empty(shape) if len(shape) < 3 else np.broadcast_to(0, shape)
            self.assertLessEqual(data[sample_selection(shape, 64)].size, 64)


if __name__ == '__main__':
    unittest.main()

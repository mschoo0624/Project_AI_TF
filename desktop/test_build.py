import importlib.util
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

spec = importlib.util.spec_from_file_location('desktop_build', Path(__file__).with_name('build.py'))
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class BuildTests(unittest.TestCase):
    def test_snapshot_keeps_committed_wal_and_does_not_change_source(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source.db'
            target = Path(folder) / 'seed.db'
            with closing(sqlite3.connect(source)) as db:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('CREATE TABLE sample (value TEXT)')
                db.execute("INSERT INTO sample VALUES ('original')")
                db.commit()
                build.snapshot(source, target)
                with closing(sqlite3.connect(target)) as copy:
                    self.assertEqual(copy.execute('SELECT value FROM sample').fetchone()[0], 'original')
                    copy.execute("UPDATE sample SET value='demo change'")
                    copy.commit()
                self.assertEqual(db.execute('SELECT value FROM sample').fetchone()[0], 'original')

    def test_unreferenced_public_assets_are_excluded(self):
        with tempfile.TemporaryDirectory() as folder:
            public, built = Path(folder) / 'public', Path(folder) / 'built'
            public.mkdir(); built.mkdir()
            (public / 'used.png').write_bytes(b'image')
            (public / 'unused.png').write_bytes(b'unused')
            (public / 'unused.pdf').write_bytes(b'pdf')
            (built / 'app.js').write_text('const src="/used.png";', encoding='utf-8')
            self.assertEqual(build.referenced_public_files(public, built), ['used.png'])
            self.assertTrue((built / 'used.png').exists())
            self.assertFalse((built / 'unused.png').exists())
            self.assertFalse((built / 'unused.pdf').exists())


if __name__ == '__main__':
    unittest.main()

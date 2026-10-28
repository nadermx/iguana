"""/upload/ in pieces (any size), /videos/ (the owner's uploaded videos) and the site's public video list."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from api.videos_views import parse_time
from catalog import videos
from catalog.models import SiteVideo

KEY = 'ipk_test'
User = get_user_model()


class Dirs(TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.drop, self.chat, self.site = (os.path.join(self.root, n) for n in ('drop', 'chat', 'site'))
        override = override_settings(DROP_PIN='1357', DROP_DIR=self.drop, CHAT_FILES_DIR=self.chat,
                                     SITE_VIDEOS_DIR=self.site, NOTIFY_EMAILS=['hello@example.com'],
                                     PUBLIC_API_KEYS=[KEY])
        override.enable()
        self.addCleanup(override.disable)


class ChunkedUploadTests(Dirs):
    """A file of any size arrives in pieces, a resent piece replaces itself, and a gap is reported, not filled."""

    def setUp(self):
        super().setUp()
        self.client.post('/upload/', {'pin': '1357'})
        self.id = 'a' * 32

    def chunk(self, offset, data, upload=None):
        return self.client.post('/upload/', {'action': 'chunk', 'upload': upload or self.id, 'offset': offset,
                                             'chunk': SimpleUploadedFile('blob', data)})

    def test_pieces_resend_and_finish_into_the_agent_folder_as_a_video(self):
        self.assertEqual(self.chunk(0, b'abcd').json(), {'have': 4})
        self.assertEqual(self.chunk(0, b'abcd').json(), {'have': 4})  # the same piece again, after a timeout
        gap = self.chunk(9, b'zz')
        self.assertEqual(gap.status_code, 409)
        self.assertEqual(gap.json(), {'have': 4})
        self.assertEqual(self.chunk(4, b'efgh').json(), {'have': 8})
        done = self.client.post('/upload/', {'action': 'finish', 'kind': 'site', 'note': 'for the home page',
                                             'files': json.dumps([{'upload': self.id, 'name': 'Show night.MOV', 'size': 8}])})
        self.assertEqual(done.status_code, 200)
        self.assertIn('sent=site', done.json()['redirect'])
        names = sorted(os.listdir(os.path.join(self.chat, 'upload')))
        self.assertTrue(names[0].endswith('__Show_night.MOV'))
        with open(os.path.join(self.chat, 'upload', names[0]), 'rb') as fh:
            self.assertEqual(fh.read(), b'abcdefgh')
        self.assertEqual(os.listdir(os.path.join(self.drop, '.parts')), [])
        video = SiteVideo.objects.get()
        self.assertEqual((video.status, video.title, video.published), (SiteVideo.PENDING, 'Show night', False))

    def test_a_short_file_is_refused_at_finish(self):
        self.chunk(0, b'abc')
        done = self.client.post('/upload/', {'action': 'finish', 'kind': 'site',
                                             'files': json.dumps([{'upload': self.id, 'name': 'x.mp4', 'size': 10}])})
        self.assertEqual(done.status_code, 400)
        self.assertFalse(SiteVideo.objects.exists())

    def test_documents_stay_private_and_are_not_videos(self):
        self.chunk(0, b'%PDF')
        done = self.client.post('/upload/', {'action': 'finish', 'kind': 'csf',
                                             'files': json.dumps([{'upload': self.id, 'name': 'c.pdf', 'size': 4}])})
        self.assertEqual(done.status_code, 200)
        stored = [n for n in os.listdir(self.drop) if n.endswith('__csf__c.pdf')]
        self.assertEqual(len(stored), 1)
        self.assertEqual(os.stat(os.path.join(self.drop, stored[0])).st_mode & 0o777, 0o600)
        self.assertFalse(SiteVideo.objects.exists())

    def test_pieces_need_the_pin(self):
        self.client.logout()
        self.client.session.flush()
        other = self.client_class()
        response = other.post('/upload/', {'action': 'chunk', 'upload': self.id, 'offset': 0,
                                           'chunk': SimpleUploadedFile('blob', b'x')})
        self.assertEqual(response.status_code, 403)

    def test_a_bad_upload_id_is_refused(self):
        self.assertEqual(self.chunk(0, b'x', upload='../../etc/passwd').status_code, 400)

    def test_a_plain_form_post_of_a_video_is_registered_too(self):
        self.client.post('/upload/', {'kind': 'site', 'files': SimpleUploadedFile('clip.mp4', b'\x00\x00\x00\x14ftyp')})
        self.assertEqual(SiteVideo.objects.get().original_name, 'clip.mp4')


class VideosPageTests(Dirs):
    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_superuser('owner', 'owner@iguanacomedy.com', 'pw')
        self.video = SiteVideo.objects.create(source=os.path.join(self.chat, 'v.mov'), original_name='v.mov', title='Set')

    def post(self, **fields):
        return self.client.post('/videos/', dict(id=self.video.pk, **fields))

    def test_owner_only(self):
        self.assertEqual(self.client.get('/videos/').status_code, 302)
        staff = User.objects.create_user('manager', '', 'pw', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get('/videos/').status_code, 302)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get('/videos/'), 'v.mov')
        self.assertContains(self.client.get('/videos/?lang=es'), 'Mostrar en el sitio')

    def test_only_a_ready_video_goes_on_the_site(self):
        self.client.force_login(self.owner)
        self.post(action='save', title='Best of', title_es='Lo mejor', published='on', position='2')
        self.video.refresh_from_db()
        self.assertFalse(self.video.published)
        self.assertEqual(self.video.title_es, 'Lo mejor')
        SiteVideo.objects.filter(pk=self.video.pk).update(status=SiteVideo.READY, web_file='x.mp4', poster_file='x.jpg')
        self.post(action='save', title='Best of', published='on')
        self.video.refresh_from_db()
        self.assertTrue(self.video.published)
        listed = self.client.get('/api/public/v1/videos?locale=es', HTTP_AUTHORIZATION=f'Bearer {KEY}').json()
        self.assertEqual(listed['videos'][0]['url'], '/site-videos/x.mp4')
        self.post(action='save', title='Best of')
        listed = self.client.get('/api/public/v1/videos', HTTP_AUTHORIZATION=f'Bearer {KEY}').json()
        self.assertEqual(listed['videos'], [])

    def test_trim_queues_a_new_copy_and_keeps_times(self):
        self.client.force_login(self.owner)
        SiteVideo.objects.filter(pk=self.video.pk).update(status=SiteVideo.READY)
        self.post(action='trim', start='0:12', end='1:45')
        self.video.refresh_from_db()
        self.assertEqual((self.video.trim_start, self.video.trim_end, self.video.status), (12, 105, SiteVideo.PENDING))
        self.post(action='trim', start='2:00', end='1:00')
        self.video.refresh_from_db()
        self.assertEqual(self.video.trim_end, 105)

    def test_delete_moves_the_original_to_the_trash(self):
        os.makedirs(self.chat)
        open(self.video.source, 'wb').close()
        self.client.force_login(self.owner)
        self.post(action='delete')
        self.assertFalse(SiteVideo.objects.exists())
        self.assertTrue(os.path.exists(os.path.join(self.chat, '.trash', 'v.mov')))

    def test_parse_time(self):
        self.assertEqual(parse_time('75'), 75)
        self.assertEqual(parse_time('1:15'), 75)
        self.assertEqual(parse_time('1:01:15'), 3675)
        self.assertEqual(parse_time('1,5'), 1.5)
        self.assertIsNone(parse_time(''))
        with self.assertRaises(ValueError):
            parse_time('soon')


@unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg is not installed')
class ProcessTests(Dirs):
    def test_a_phone_video_becomes_a_web_copy_with_a_poster_and_a_trim(self):
        os.makedirs(self.chat)
        source = os.path.join(self.chat, 'clip.mov')
        subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'testsrc=size=320x568:rate=10',
                        '-f', 'lavfi', '-i', 'sine', '-t', '4', '-c:v', 'mpeg4', '-c:a', 'aac', source], check=True)
        video = videos.register(source, 'clip.mov')
        videos.process(video)
        video.refresh_from_db()
        self.assertEqual(video.status, SiteVideo.READY, video.error)
        self.assertAlmostEqual(video.duration, 4, delta=0.3)
        self.assertTrue(os.path.exists(os.path.join(self.site, video.poster_file)))
        first = video.web_file
        video.trim_start, video.trim_end = 1, 3
        video.save()
        videos.process(video)
        video.refresh_from_db()
        self.assertAlmostEqual(video.duration, 2, delta=0.3)
        self.assertFalse(os.path.exists(os.path.join(self.site, first)))
        self.assertTrue(os.path.exists(source))

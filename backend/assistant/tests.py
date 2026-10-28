import json
import sys

from django.contrib.auth import get_user_model
from django.test import TestCase

from assistant.management.commands.chat_worker import claim_next
from assistant.models import Conversation, Turn
from assistant.runner import TurnState, describe_tool, run_turn

User = get_user_model()

# Stands in for `iguana-agent-run`: reads the prompt on stdin and prints Claude Code's stream-json.
FAKE_AGENT = r'''
import json, sys
session = sys.argv[-1]
prompt = sys.stdin.read()
def out(event): print(json.dumps(event), flush=True)
out({"type": "system", "subtype": "init", "session_id": session})
if "fail" in prompt:
    out({"type": "result", "subtype": "success", "is_error": True, "result": "Invalid API key, please run /login"})
    sys.exit(1)
out({"type": "assistant", "message": {"content": [
    {"type": "text", "text": "Looking."},
    {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "git status", "description": "Check the tree"}},
    {"type": "tool_use", "id": "t2", "name": "Read", "input": {"file_path": "/home/claude/iguana/README.md"}}]}})
out({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t2", "is_error": True}]}})
out({"type": "result", "subtype": "success", "result": "Done. prompt=%s session=%s" % (prompt, session),
     "total_cost_usd": 0.01234})
'''


class ChatAccessTests(TestCase):
    """Only a superuser reaches /chat/: it drives an agent that can deploy and read every booking."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_superuser('owner', 'owner@iguanacomedy.com', 'pw')
        cls.staff = User.objects.create_user('manager', 'manager@iguanacomedy.com', 'pw', is_staff=True)
        cls.floor = User.objects.create_user('mesero', '', 'pw')

    def test_page_is_owner_only(self):
        self.assertRedirects(self.client.get('/chat/'), '/admin/login/?next=/chat/', fetch_redirect_response=False)
        for user in (self.staff, self.floor):
            self.client.force_login(user)
            self.assertEqual(self.client.get('/chat/').status_code, 302)
        self.client.force_login(self.owner)
        page = self.client.get('/chat/')
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'chat-data')

    def test_json_endpoints_refuse_non_owners_without_redirecting(self):
        conversation = Conversation.objects.create(title='x')
        turn = Turn.objects.create(conversation=conversation, prompt='hi')
        for user in (None, self.staff, self.floor):
            if user:
                self.client.force_login(user)
            self.assertEqual(self.client.post('/chat/send/', '{"prompt": "hi"}', content_type='application/json').status_code, 403)
            self.assertEqual(self.client.get(f'/chat/{conversation.pk}/turns/').status_code, 403)
            self.assertEqual(self.client.post(f'/chat/turn/{turn.pk}/stop/').status_code, 403)
        self.assertEqual(Turn.objects.count(), 1)

    def test_spanish_page(self):
        self.client.force_login(self.owner)
        page = self.client.get('/chat/', HTTP_ACCEPT_LANGUAGE='es-MX')
        self.assertContains(page, 'Conversación nueva')
        self.assertContains(page, 'Enviar')


class ChatFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_superuser('owner', 'owner@iguanacomedy.com', 'pw')

    def setUp(self):
        self.client.force_login(self.owner)

    def send(self, **body):
        return self.client.post('/chat/send/', json.dumps(body), content_type='application/json')

    def test_old_conversations_stay_in_the_picker(self):
        made = [Conversation.objects.create(title=f'talk {i}') for i in range(35)]
        page = self.client.get('/chat/')
        self.assertContains(page, f'value="{made[0].pk}"')
        self.assertEqual(self.client.get(f'/chat/?c={made[0].pk}').status_code, 200)

    def test_send_queues_a_turn_and_one_at_a_time(self):
        first = self.send(prompt='  Add a show on Friday  ').json()
        conversation = Conversation.objects.get(pk=first['conversation'])
        self.assertEqual(conversation.title, 'Add a show on Friday')
        turn = conversation.turns.get()
        self.assertEqual((turn.prompt, turn.status), ('Add a show on Friday', Turn.QUEUED))
        self.assertEqual(self.send(conversation=conversation.pk, prompt='and another').status_code, 409)
        self.assertEqual(self.send(prompt='').status_code, 400)

        listed = self.client.get(f'/chat/{conversation.pk}/turns/').json()['turns']
        self.assertEqual([t['status'] for t in listed], ['queued'])

    def test_stop_a_queued_turn(self):
        conversation = self.send(prompt='hello').json()['conversation']
        turn = Turn.objects.get(conversation=conversation)
        self.client.post(f'/chat/turn/{turn.pk}/stop/')
        turn.refresh_from_db()
        self.assertEqual(turn.status, Turn.STOPPED)
        self.assertIsNotNone(turn.finished_at)
        self.assertIsNone(claim_next())


class ChatAttachmentTests(TestCase):
    """Files attached in /chat/ are saved where the agent can read them, and the prompt says where."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_superuser('owner', 'owner@iguanacomedy.com', 'pw')

    def setUp(self):
        import tempfile
        from django.test import override_settings
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        override = override_settings(CHAT_FILES_DIR=self.tmp.name)
        override.enable()
        self.addCleanup(override.disable)
        self.client.force_login(self.owner)

    def test_attachments_are_saved_and_listed_in_the_prompt(self):
        import os
        from django.core.files.uploadedfile import SimpleUploadedFile
        body = self.client.post('/chat/send/', {
            'prompt': 'Put this menu on the bar page',
            'files': [SimpleUploadedFile('../menu octubre.pdf', b'%PDF-1.4 x', 'application/pdf'),
                      SimpleUploadedFile('poster.jpg', b'\xff\xd8\xff', 'image/jpeg')],
        }).json()
        turn = Turn.objects.get(pk=body['turn']['id'])
        folder = os.path.join(self.tmp.name, 'chat', str(body['conversation']))
        names = sorted(os.listdir(folder))
        self.assertEqual(len(names), 2)
        self.assertTrue(turn.prompt.startswith('Put this menu on the bar page\n\nAttached files:\n'))
        for name in names:
            self.assertIn(os.path.join(folder, name), turn.prompt)
            self.assertNotIn('/', name)

    def test_files_alone_are_a_message(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        body = self.client.post('/chat/send/', {'files': SimpleUploadedFile('clip.mp4', b'x', 'video/mp4')}).json()
        self.assertEqual(Conversation.objects.get(pk=body['conversation']).title, 'clip.mp4')
        self.assertIn('Attached files:', Turn.objects.get(pk=body['turn']['id']).prompt)

    def test_signed_out_cannot_attach(self):
        import os
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.logout()
        response = self.client.post('/chat/send/', {'files': SimpleUploadedFile('x.pdf', b'x')})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(os.listdir(self.tmp.name), [])


class RunnerTests(TestCase):
    def setUp(self):
        self.command = [sys.executable, '-c', FAKE_AGENT]
        self.conversation = Conversation.objects.create(title='t')

    def run_one(self, prompt):
        Turn.objects.create(conversation=self.conversation, prompt=prompt)
        turn = claim_next()
        self.assertEqual(turn.status, Turn.RUNNING)
        run_turn(turn, command=self.command)
        turn.refresh_from_db()
        return turn

    def test_a_turn_runs_to_done(self):
        turn = self.run_one('check the site')
        self.assertEqual(turn.status, Turn.DONE)
        self.assertIn('Done. prompt=check the site', turn.reply)
        self.assertIn(f'session={self.conversation.session_id}', turn.reply)
        self.assertEqual([a['text'] for a in turn.activity], ['Bash: Check the tree', 'Read: /home/claude/iguana/README.md'])
        self.assertTrue(turn.activity[1].get('error'))
        self.assertEqual(str(turn.cost_usd), '0.0123')
        self.assertIsNotNone(turn.finished_at)

    def test_an_agent_error_fails_the_turn_with_the_reason(self):
        turn = self.run_one('fail please')
        self.assertEqual(turn.status, Turn.FAILED)
        self.assertIn('/login', turn.error)

    def test_a_missing_command_fails_cleanly(self):
        Turn.objects.create(conversation=self.conversation, prompt='hi')
        turn = claim_next()
        run_turn(turn, command=['/nonexistent/iguana-agent-run'])
        turn.refresh_from_db()
        self.assertEqual(turn.status, Turn.FAILED)
        self.assertIn('Could not start', turn.error)


class StreamParsingTests(TestCase):
    def test_describe_tool(self):
        self.assertEqual(describe_tool('Bash', {'command': 'ls -la'}), 'Bash: ls -la')
        self.assertEqual(describe_tool('Edit', {'file_path': '/a/b.py'}), 'Edit: /a/b.py')
        self.assertEqual(describe_tool('TodoWrite', {}), 'TodoWrite')

    def test_text_without_result_still_becomes_the_reply(self):
        state = TurnState()
        state.feed('not json')
        state.feed(json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'Partial'}]}}))
        self.assertEqual(state.reply, 'Partial')

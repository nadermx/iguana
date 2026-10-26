"""Offline tests for the /chat/ agent's guardrails (ansible/files/agent/guard.py and pii_scan.py). No network.

    python3 -m unittest discover -s scripts/tests -v
"""

import importlib.util
import pathlib
import subprocess
import unittest

AGENT = pathlib.Path(__file__).resolve().parents[2] / 'ansible' / 'files' / 'agent'


def load(name):
    spec = importlib.util.spec_from_file_location(name, AGENT / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = load('guard')
pii = load('pii_scan')


class GuardTests(unittest.TestCase):
    def blocked(self, command):
        return guard.check('Bash', {'command': command})

    def test_the_owner_s_ordinary_work_runs(self):
        for command in (
            'git status', 'git push origin backend-django', 'git push origin backend-django:main',
            'git commit -m "Friday show added"', 'sudo iguana-agent-deploy', 'sudo iguana-agent-deploy --commit abc123',
            'iguana-manage shell -c "print(1)"', 'sudo -u iguana psql iguana -c "select count(*) from sales_order"',
            'rm -rf node_modules', 'rm -rf /tmp/build', 'rm -r backend/assistant/__pycache__',
            'sudo supervisorctl restart iguana:iguana-web', 'ls -la /var/backups/iguana 2>&1',
            'cat /var/backups/iguana/LAST_OK', 'cat /etc/claude-code/managed-settings.json',
            'python3 scripts/meta-ads.py status', 'curl -s https://iguanacomedy.com/en/ > /dev/null',
            'iguana-manage changepassword andrew', 'sudo -u iguana psql iguana -c "update catalog_event set status=1"',
        ):
            self.assertIsNone(self.blocked(command), command)

    def test_what_cannot_be_undone_is_blocked(self):
        for command in (
            'git push --force origin backend-django', 'git push -f', 'git push origin +backend-django',
            'git push origin :main', 'git push --delete origin main', 'git push --mirror',
            'git filter-branch --env-filter x', 'git commit --no-verify -m x', 'git -c core.hooksPath=/dev/null commit',
            'sudo -u postgres dropdb iguana', 'psql -c "DROP TABLE sales_order"', 'psql -c "truncate sales_order"',
            'iguana-manage flush --noinput', 'venv/bin/python manage.py flush', 'iguana-manage migrate sales zero',
            'sudo rm -rf /home/www/iguana', 'sudo rm -rf /var/backups/iguana/', 'rm -fr ~', 'sudo rm -r -f /',
            'timeout 30 sudo rm -Rf /home/www/iguana/backend/media', 'rm -rf /home/claude/iguana/.git',
            'sudo ufw disable', 'sudo passwd iguana', 'sudo shutdown -h now', 'crontab -r',
            'sudo rm /etc/claude-code/managed-settings.json', 'echo {} | sudo tee /etc/claude-code/managed-settings.json',
            'sudo sed -i s/x/y/ /usr/local/lib/iguana-agent/guard.py', 'sudo rm /var/backups/iguana/daily/x.sql.gz',
            'sudo cp x /etc/sudoers.d/claude', 'sudo rm -rf /var/lib/iguana/chat-files',
            'sudo mv /etc/cron.d/iguana-backup /tmp',
        ):
            self.assertIsNotNone(self.blocked(command), command)

    def test_file_tools_cannot_edit_the_guardrails(self):
        for path in ('/etc/claude-code/managed-settings.json', '/usr/local/lib/iguana-agent/pii_scan.py',
                     '/home/claude/iguana/.git/hooks/pre-commit', '/etc/sudoers.d/iguana-agent'):
            self.assertIsNotNone(guard.check('Write', {'file_path': path}), path)
        self.assertIsNone(guard.check('Edit', {'file_path': '/home/claude/iguana/src/pages/en/index.astro'}))

    def test_hook_exit_code(self):
        run = lambda command: subprocess.run(
            ['python3', str(AGENT / 'guard.py')], input=f'{{"tool_name": "Bash", "tool_input": {{"command": "{command}"}}}}',
            capture_output=True, text=True)
        self.assertEqual(run('git status').returncode, 0)
        refused = run('git push --force')
        self.assertEqual(refused.returncode, 2)
        self.assertIn('Blocked by the server guard', refused.stderr)


class PiiScanTests(unittest.TestCase):
    PEOPLE = ({'fan.one@company.invalid', 'fan@company.invalid'}, {'9840000123'})

    def problems(self, text, repo=frozenset()):
        return pii.problems(text, *self.PEOPLE, already_in_repo=repo)

    def test_clean_text_passes(self):
        self.assertEqual(self.problems('Contact hello@iguanacomedy.com or someone@example.com; 80 seats.'), [])
        self.assertEqual(self.problems('Co-Authored-By: Claude <noreply@anthropic.com>'), [])

    def test_a_real_customer_is_refused_and_masked_in_the_message(self):
        found = self.problems("contact = Contact(email='Fan.One@Company.invalid')")
        self.assertEqual(len(found), 1)
        self.assertIn('real customer', found[0])
        self.assertNotIn('fan.one', found[0])
        self.assertTrue(self.problems('fan@company.invalid bounced twice'))

    def test_customer_phone_in_any_format(self):
        self.assertTrue(self.problems('called +52 (984) 000-0123 about the refund'))
        self.assertEqual(self.problems('order 2026102512 total 984'), [])

    def test_new_webmail_address_is_refused_unless_already_a_fixture(self):
        self.assertTrue(self.problems('zq7-not-a-person@hotmail.com'))
        self.assertEqual(self.problems('typo@gmail.com', repo=frozenset({'typo@gmail.com'})), [])

    def test_secrets(self):
        for text in ('sk_live_' + 'a' * 24, 'whsec_' + 'b' * 24, 'EAA' + 'c' * 80, 'ghp_' + 'd' * 36,
                     '-----BEGIN OPENSSH PRIVATE KEY-----'):
            self.assertTrue(self.problems(text), text)

    def test_unreadable_database_refuses(self):
        class Failed:
            returncode, stdout, stderr = 1, '', 'peer authentication failed'
        with self.assertRaises(RuntimeError):
            pii.load_people(runner=lambda *a, **k: Failed())

        class Empty:
            returncode, stdout, stderr = 0, '', ''
        with self.assertRaises(RuntimeError):
            pii.load_people(runner=lambda *a, **k: Empty())

    def test_people_are_parsed(self):
        class Rows:
            returncode, stderr = 0, ''
            stdout = 'a@b.invalid\t\n\t+52 984 000 0123\nC@D.INVALID\t555\n'
        emails, phones = pii.load_people(runner=lambda *a, **k: Rows())
        self.assertEqual(emails, {'a@b.invalid', 'c@d.invalid'})
        self.assertEqual(phones, {'9840000123'})


if __name__ == '__main__':
    unittest.main()

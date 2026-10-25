"""The owner's chat with the Claude Code instance that runs the site (`/chat/`, docs/chat-agent.md).

A browser never talks to Claude. It writes a `Turn` and polls it; `manage.py chat_worker` (its own supervisor
program) picks the turn up, runs Claude Code as the unprivileged `claude` user and writes what happens back onto
the row. That keeps a turn that runs for twenty minutes off gunicorn's three sync workers, and it means the whole
conversation, every tool the agent ran included, lives in Postgres and is in the nightly backup.
"""

import uuid

from django.conf import settings
from django.db import models


class Conversation(models.Model):
    title = models.CharField(max_length=120, blank=True)
    # The Claude Code session this conversation resumes, so the agent remembers the earlier turns.
    session_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.title or f'Conversation {self.pk}'


class Turn(models.Model):
    QUEUED, RUNNING, DONE, FAILED, STOPPED = 'queued', 'running', 'done', 'failed', 'stopped'
    STATUS_CHOICES = [(QUEUED, 'Queued'), (RUNNING, 'Running'), (DONE, 'Done'), (FAILED, 'Failed'),
                      (STOPPED, 'Stopped')]
    FINISHED = (DONE, FAILED, STOPPED)

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='turns')
    prompt = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=QUEUED, db_index=True)
    reply = models.TextField(blank=True)
    # What the agent did along the way, one short line per tool call: [{"kind": "tool", "text": "Bash: git status"}].
    activity = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    cost_usd = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    stop_requested = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at', 'pk']

    def __str__(self):
        return f'{self.conversation_id}/{self.pk} {self.status}'

    @property
    def finished(self):
        return self.status in self.FINISHED

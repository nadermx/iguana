"""/chat/: the owner talks to the Claude Code instance that runs the site (docs/chat-agent.md).

Superusers only. The agent can change code, deploy and read every booking, so the gate is the strongest account
type there is, not `is_staff` (which the bar and door accounts never have, but which a future manager might).

Nothing here waits on Claude. A message becomes a queued `Turn`, `manage.py chat_worker` runs it, and the page
polls every two seconds, because gunicorn has three sync workers and a held-open request would take a third of
the checkout's capacity for as long as the agent works.
"""

import json

from django.contrib.auth.decorators import user_passes_test
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from assistant.models import Conversation, Turn
from sales.i18n import lang_from_request, tr

MAX_PROMPT = 20000


def is_owner(user):
    return user.is_active and user.is_superuser


def _owner_json(view):
    """JSON endpoints answer 403 rather than redirect: a fetch() that follows a redirect to a login form reads
    an HTML page as JSON and fails without saying why."""
    def wrapped(request, *args, **kwargs):
        if not is_owner(request.user):
            return JsonResponse({'error': 'Not allowed'}, status=403)
        return view(request, *args, **kwargs)
    wrapped.__name__ = view.__name__
    return wrapped


def _turn(turn):
    return {
        'id': turn.pk,
        'prompt': turn.prompt,
        'status': turn.status,
        'reply': turn.reply,
        'activity': turn.activity,
        'error': turn.error,
        'cost': str(turn.cost_usd) if turn.cost_usd is not None else None,
        'created': turn.created_at.isoformat(),
        'finished': turn.finished,
    }


@user_passes_test(is_owner, login_url='/admin/login/')
@require_GET
def chat(request):
    lang = lang_from_request(request)
    conversations = list(Conversation.objects.all()[:30])
    current = None
    if request.GET.get('c'):
        current = get_object_or_404(Conversation, pk=request.GET['c']) if request.GET['c'].isdigit() else None
        if current is None:
            raise Http404
    elif not request.GET.get('new') and conversations:
        current = conversations[0]
    turns = [_turn(t) for t in current.turns.all()] if current else []
    busy = Turn.objects.filter(status__in=(Turn.QUEUED, Turn.RUNNING)).exclude(conversation=current).exists()
    strings = {key: tr(lang, text) for key, text in {
        'queued': 'Waiting for the agent…',
        'running': 'Working…',
        'stopped': 'Stopped.',
        'failed': 'Failed',
        'stop': 'Stop',
        'steps': '{0} steps',
        'send_failed': 'Could not send. Check the connection and try again.',
    }.items()}
    return render(request, 'embed/chat.html', {
        'lang': lang,
        'conversations': conversations,
        'current': current,
        'busy_elsewhere': busy,
        'bootstrap': {'conversation': current.pk if current else None, 'turns': turns, 'strings': strings},
    })


@_owner_json
@require_POST
def send(request):
    try:
        body = json.loads(request.body or b'{}')
    except ValueError:
        return JsonResponse({'error': 'Invalid request'}, status=400)
    prompt = str(body.get('prompt') or '').strip()
    if not prompt:
        return JsonResponse({'error': 'Write a message first'}, status=400)
    if len(prompt) > MAX_PROMPT:
        return JsonResponse({'error': 'That message is too long'}, status=400)
    if body.get('conversation'):
        conversation = get_object_or_404(Conversation, pk=body['conversation'])
    else:
        conversation = Conversation.objects.create(title=' '.join(prompt.split())[:120], created_by=request.user)
    if conversation.turns.filter(status__in=(Turn.QUEUED, Turn.RUNNING)).exists():
        return JsonResponse({'error': 'Wait for the current reply to finish, or stop it'}, status=409)
    turn = Turn.objects.create(conversation=conversation, prompt=prompt, created_by=request.user)
    conversation.save(update_fields=['updated_at'])
    return JsonResponse({'conversation': conversation.pk, 'turn': _turn(turn)})


@_owner_json
@require_GET
def turns(request, conversation_id):
    conversation = get_object_or_404(Conversation, pk=conversation_id)
    return JsonResponse({'turns': [_turn(t) for t in conversation.turns.all()]})


@_owner_json
@require_POST
def stop(request, turn_id):
    turn = get_object_or_404(Turn, pk=turn_id)
    if turn.status == Turn.QUEUED:
        Turn.objects.filter(pk=turn.pk, status=Turn.QUEUED).update(status=Turn.STOPPED, stop_requested=True,
                                                                         finished_at=timezone.now())
    elif turn.status == Turn.RUNNING:
        Turn.objects.filter(pk=turn.pk).update(stop_requested=True)
    return JsonResponse({'ok': True})

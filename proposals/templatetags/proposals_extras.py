from django import template
from urllib.parse import urlencode

register = template.Library()

@register.simple_tag
def msg_can_update(msg, user):
    return msg.can_update(user)

@register.simple_tag
def msg_can_update_full(msg, user):
    return msg.can_update_full(user)

@register.simple_tag
def msg_my_vote(msg, user):
    return msg.my_vote(user)

@register.simple_tag
def msg_funds_personal(msg, user):
    return msg.funds_collected_personal(user)

@register.simple_tag
def sort_is_hot(sort_mode, has_rank):
    return sort_mode == 'hot' or (not sort_mode and not has_rank)

@register.simple_tag
def children_sorted(msg, sort_mode, user, filter_mode):
    return msg.children_sorted(sort_mode, user, filter_mode)

@register.simple_tag
def pending_diff(msg, can_update_full):
    pending = msg.pending_edit()
    if(pending):
        return msg.diff(pending, can_update_full)
    return None

@register.simple_tag
def msg_pending_or_self(msg):
    if msg.has_pending_edit:
        pending = msg.pending_edit()
        if pending:
            return pending
    return msg

@register.simple_tag
def my_notifications(msg, user):
    return msg.notifications.filter(
        recipient=user,
    )

@register.simple_tag
def urlparams(*_, **kwargs):
    safe_args = {k: v for k, v in kwargs.items() if v is not None}
    if safe_args:
        return '?{}'.format(urlencode(safe_args))
    return ''

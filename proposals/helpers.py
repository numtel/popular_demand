from django.shortcuts import _get_queryset
from django.db.models import When, Case, F, Func, FloatField, ExpressionWrapper
from django.contrib.auth.models import Group
from django.http import HttpResponseRedirect
from django.urls import reverse

def is_mod(request_or_user):
    if hasattr(request_or_user, 'user'):
        user = request_or_user.user
    else:
        user = request_or_user
    if not user.is_authenticated:
        return False
    moderator_group, _ = Group.objects.get_or_create(name='moderator')
    return user.groups.filter(name=moderator_group).exists()

def redirect_qd(viewname, *args, qd=None, **kwargs):
    rev = reverse(viewname, *args, **kwargs)
    if qd:
        rev = '{}?{}'.format(rev, qd.urlencode())
    return HttpResponseRedirect(rev)


def get_object_or_None(klass, *args, **kwargs):
    """
    Uses get() to return an object or None if the object does not exist.

    klass may be a Model, Manager, or QuerySet object. All other passed
    arguments and keyword arguments are used in the get() query.

    Note: Like with get(), a MultipleObjectsReturned will be raised if more than one
    object is found.
    """
    queryset = _get_queryset(klass)
    try:
        return queryset.get(*args, **kwargs)
    except queryset.model.DoesNotExist:
        return None

def get_display_rank():
    return Case(
        # Time increases the value when the score is negative
        When(vote_score__lt=0, then=ExpressionWrapper(F('vote_score') * Func(
            Func(F('created'),
                function='AGE',
                template='%(function)s(current_timestamp, %(expressions)s)',
            ),
            function='EXTRACT',
            template='%(function)s(epoch from %(expressions)s)',
        ), output_field=FloatField())),
        # Time decreases the value when the score is positive
        When(vote_score__gt=0, then=ExpressionWrapper(F('vote_score') / Func(
            Func(F('created'),
                function='AGE',
                template='%(function)s(current_timestamp, %(expressions)s)',
            ),
            function='EXTRACT',
            template='%(function)s(epoch from %(expressions)s)',
        ), output_field=FloatField())),
        default=0,
        output_field=FloatField(),
    )

# XXX function name should be get_all_active_funded_msg
def get_all_funded_msg(user, omit_msg=None):
    all_funded_msg = []
    for msg_tx in user.msg_tx.select_related('msg').order_by('-created'):
        msg_tx_msg_funds_personal = msg_tx.msg.funds_collected_personal(user)
        if (not msg_tx.msg in all_funded_msg) \
                and ((not omit_msg) or (msg_tx.msg.pk is not omit_msg.pk)) \
                and (not msg_tx.msg.is_bid or msg_tx.msg.bid_remaining() > 0) \
                and not msg_tx.msg.paid() \
                and not msg_tx.msg.fulfilled() \
                and (msg_tx_msg_funds_personal > 0):
            msg_tx.msg.funds_personal = msg_tx_msg_funds_personal
            all_funded_msg.append(msg_tx.msg)
    return all_funded_msg

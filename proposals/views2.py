from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.http.request import QueryDict
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.translation import gettext
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

import stripe
import pprint
pp = pprint.PrettyPrinter(width=100, compact=True)

from .models2 import MsgStatus, MsgTxStatus, MsgTx, MsgVote, Msg, \
    apply_sort_and_filter, MsgNotificationKlass, MsgNotification
from .helpers import get_object_or_None, get_display_rank, is_mod, redirect_qd, \
    get_all_funded_msg

def handle_msg_action(request):
    if request.method == 'GET':
        action = request.GET.get('action')
    elif request.method == 'POST':
        # POST will be single field with msg.pk as param value
        action, param = list(filter(
            lambda tup: tup[0] != 'csrfmiddlewaretoken',
            request.POST.items()))[0]

    vote_actions = {
        'upvote': 1,
        'neutralvote': 0,
        'downvote': -1,
    }

    moderator_actions = {
        'approve': MsgStatus.ACTIVE.value,
        'decline': MsgStatus.DECLINED.value,
        'fulfilled': MsgStatus.FULFILLED.value,
    }

    if action and not request.user.is_authenticated:
        return 'login'
    elif action == 'msg_create':
        return 'proposals:msg_create'
    elif action == 'dismiss_notif':
        notif = get_object_or_404(MsgNotification, pk=param)
        if request.user == notif.recipient:
            notif.delete()
    elif isinstance(action, str):
        msg = get_object_or_404(Msg, pk=param)
        if action in vote_actions:
            msg.set_my_vote(request.user, vote_actions[action])
        elif action == 'approve_edit':
            msg.approve_edit(request)
        elif action == 'bid_payout':
            # TODO move stripe operation to msg.set_status
            if not is_mod(request.user):
                messages.error(request, gettext('Unauthorized'))
            elif not msg.bid_pending_payout():
                messages.error(request, gettext('Invalid action'))
            else:
                amount = int(msg.funds_collected_all() *
                    settings.PAYOUT_PROPORTION)
                stripe_transfer = stripe.Transfer.create(
                    amount=amount,
                    currency='usd',
                    destination=msg.creator.stripe.connect_account,
                    transfer_group=msg.pk
                )
                msg.set_status(MsgStatus.PAID.value)
                messages.success(request, gettext('Bid paid'))
        elif action in moderator_actions:
            if not is_mod(request.user):
                messages.error(request, gettext('Unauthorized'))
            else:
                msg.set_status(moderator_actions[action])
        return msg
    return None

# 2nd-order view handler
def msg_list(request, all_msgs, **kwargs):
    page = request.GET.get('page')
    sort_mode = request.GET.get('sort')
    filter_mode = {
        'comments': request.GET.get('hide_comments') == 'true',
        'proposals': request.GET.get('hide_proposals') == 'true',
        'bids': request.GET.get('hide_bids') == 'true',
        'pending': request.GET.get('hide_pending') == 'true',
        'declined': request.GET.get('hide_declined') == 'true',
        'unmet_bids': request.GET.get('hide_unmet_bids') == 'true',
        'pending_edit': request.GET.get('hide_pending_edit') == 'true',
        'active': request.GET.get('hide_active') == 'true',
        'paid': request.GET.get('hide_paid') == 'true',
        'fulfilled': request.GET.get('hide_fulfilled') == 'true',
    }

    action_result = handle_msg_action(request)
    if isinstance(action_result, str):
        return redirect(action_result)

    if isinstance(all_msgs, Msg):
        root = all_msgs
        if isinstance(action_result, Msg) and root.pk == action_result.pk:
            root = action_result
        all_msgs = root.children_sorted(sort_mode, request.user, filter_mode)
    else:
        root = None

    all_results = apply_sort_and_filter(
        all_msgs, request.user, sort_mode, filter_mode,
        hasattr(kwargs, 'has_rank') and kwargs['has_rank'])
    paginator = Paginator(
        all_results,
        settings.PAGINATION_SIZE)
    return render(request, 'msg/index.html', {
        'root': root,
        'msgs': paginator.get_page(page),
        'sort_mode': sort_mode,
        'filter_mode': filter_mode,
        **kwargs
    })

# Begin 1st-order views
def msg_search(request):
    # TODO moderation action doesn't show in these results on first refresh
    query_str = request.GET.get('q')
    search_root = request.GET.get('root')
    if search_root:
        search_root = get_object_or_404(Msg, pk=search_root)
    if query_str:
        results = Msg.objects.annotate(
            rank=SearchRank(
                SearchVector('title', weight='A') +
                    SearchVector('text', weight='A') +
                    SearchVector('creator__username', weight='A') +
                    SearchVector('collaborators__username', weight='A'),
                SearchQuery(query_str)
            ),
        ).filter(
            rank__gte=0.1,
        )
    else:
        results = Msg.objects.all()

    if search_root:
        results = results.filter(path__contains=[search_root.pk])

    return msg_list(request, results,
        has_rank=True if query_str else False,
        search_query=query_str,
        search_root=search_root,
        show_breadcrumbs=True,
        skip_children=True,
        title=gettext(
            'Search Results for "%s"- United Consumers of America'
        ) % (query_str) if query_str else gettext(
            'Search - United Consumers of America'
        ))

def msg_user_detail(request, username):
    user = get_object_or_404(User, username=username)
    return msg_list(request, user.msg,
        skip_children=True,
        show_breadcrumbs=True,
        heading_text=user.username,
        title=gettext(
            '%s - United Consumers of America'
        ) % (user.username))

@login_required
def msg_notifications(request):
    return msg_list(request, Msg.objects.filter(
            notifications__recipient=request.user,
        ),
        skip_children=True,
        show_breadcrumbs=True,
        show_notification_klass=True,
        title=gettext(
            'Notifications - United Consumers of America'
        ))

def msg_home(request):
    try:
        root = Msg.objects.get(pk=settings.ROOT_POST_ID)
    except:
        return redirect('proposals:msg_create')
    if not root.visible_for_me(request.user):
        return redirect('logout')
    return msg_index(request, root)

def msg_index(request, root):
    if isinstance(root, int):
        root = get_object_or_404(Msg, pk=root)
    if not root.visible_for_me(request.user):
        return redirect('proposals:index')
    return msg_list(request, root,
        max_depth=settings.INDEX_DEPTH,
        show_breadcrumbs=False,
        title=gettext(
            '%s - United Consumers of America'
        ) % (root.title))

@login_required
def msg_create(request):
    parent_id = request.GET.get('parent')
    parent = None
    if parent_id:
        parent = get_object_or_404(Msg, pk=parent_id)
    elif not is_mod(request.user):
        messages.error(request,
            gettext('Please specify a parent post with which to reply.'))
        return redirect('proposals:index')
    if parent is not None and not parent.visible_for_me(request.user):
        return redirect('proposals:index')

    msg = Msg(
        creator=request.user,
        parent=parent,
        status=MsgStatus.PENDING.value
    )
    if request.method == 'POST' and msg.post_update(request):
        return redirect(msg.href())

    return render(request, 'msg/edit.html', {
        'msg': msg,
        'parent': parent if parent_id else None,
        'connect_account_label':  request.user.stripe.connect_account_label
            if hasattr(request.user, 'stripe') else None,
    })

@login_required
def msg_edit(request):
    msg = get_object_or_404(Msg, pk=request.GET.get('msg'))
    if not msg.can_update(request.user):
        messages.error(request, gettext('Unauthorized to update this post'))
        return redirect('proposals:index')
    if not msg.visible_for_me(request.user):
        return redirect('proposals:index')
    if request.method == 'POST' and msg.post_update(request):
        return redirect(msg.href())
    return render(request, 'msg/edit.html', {
        'msg': msg,
        'og_msg': msg,
        'parent': msg.parent,
        'MsgStatus': MsgStatus,
        'connect_account_label':  request.user.stripe.connect_account_label
            if hasattr(request.user, 'stripe') else None,
    })

@login_required
def msg_fund(request, msg_id):
    msg = get_object_or_404(Msg, pk=msg_id)
    if not msg.visible_for_me(request.user):
        return redirect('proposals:msg_index')
    if not hasattr(request.user, 'stripe') \
            or request.user.stripe.customer_id is None \
            or request.user.stripe.card_id is None:
        qd = QueryDict(mutable=True)
        qd.update(next=request.get_full_path())
        return redirect_qd('proposals:profile_payment_method', qd=qd)
    if request.method == 'POST':
        total = 0
        if msg.status != MsgStatus.ACTIVE.value \
                or (msg.is_proposal == False and msg.is_bid == False):
            messages.error(request, gettext('Cannot fund inactive post'))
            return redirect(msg.href())
        for field_name, field_value in request.POST.items():
            # Migrate funds from other funds
            if field_name[:4] == 'msg_':
                migrate_from_id = int(field_name[4:])
                migrate_amount = float(field_value)
                migrate_amount_cents = int(migrate_amount * 100)
                migrate_from = get_object_or_404(Msg, pk=migrate_from_id)
                migrate_from_available = \
                    migrate_from.funds_collected_personal(request.user)
                if migrate_amount_cents > migrate_from_available:
                    messages.error(request, gettext(
                        'Insufficient amount available.'))
                    return redirect(request.get_full_path())
                if migrate_from.bid_expired() \
                        and migrate_from.bid_remaining() < 0:
                    messages.error(request, gettext(
                        'Cannot migrate from bid after its expiration ' + \
                        'over the threshold amount.'))
                    return redirect(request.get_full_path())
                if migrate_from.paid() or migrate_from.fulfilled():
                    messages.error(request, gettext(
                        'Cannot migrate from bid after payment to bidder.'))
                    return redirect(request.get_full_path())

                to_tx = MsgTx(
                    creator=request.user,
                    msg=msg,
                    amount_cents=migrate_amount_cents,
                    status=MsgTxStatus.SUCCEEDED.value,
                )
                to_tx.save()
                from_tx = MsgTx(
                    creator=request.user,
                    msg=migrate_from,
                    amount_cents=-migrate_amount_cents,
                    status=MsgTxStatus.SUCCEEDED.value,
                    next_tx=to_tx,
                )
                from_tx.save()
                total += migrate_amount_cents
        amount_raw = request.POST.get('card_amount')
        if amount_raw:
            # This migration includes a payment from a card
            amount = float(amount_raw)
            if amount < settings.MIN_FUND or amount > settings.MAX_FUND:
                messages.error(request, gettext(
                    'Invalid fund amount from credit card.'))
                return redirect(request.get_full_path())
            amount_cents = int(amount * 100)
            total += amount_cents
            payment_intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency="usd",
                confirm=True,
                customer=request.user.stripe.customer_id,
                payment_method=request.user.stripe.card_id,
                description=msg.pk,
                return_url=settings.STRIPE_PAYMENT_INTENT_RETURN_URI,
            )
            tx = MsgTx(
                creator=request.user,
                msg=msg,
                amount_cents=amount_cents,
                stripe_payment_intent_id=payment_intent['id'],
                status=MsgTxStatus.PENDING.value,
            )
            tx.save()
            if payment_intent['next_action']:
                return redirect(
                    payment_intent['next_action']['redirect_to_url']['url'])
        if total == 0:
            messages.error(request, gettext('No fund amount specified.'))
            return redirect(request.get_full_path())
        else:
            messages.success(request, gettext(
                'Fund migration successful. ' +
                'It may take a few seconds for the fund totals to update.'))
            return redirect(msg.href())

    migrate_from_any = request.GET.get('from_all') == 'true'
    return render(request, 'msg/fund.html', {
        'msg': msg,
        'page_path': request.get_full_path(),
        'migrate_from_any': migrate_from_any,
        'funded_msg': get_all_funded_msg(request.user, msg)
            if migrate_from_any else
                list(filter(lambda m: m.active() and m.funds_personal > 0,
                    msg.ancestors(request.user))),
        'card_label':  request.user.stripe.card_label,
    })

@login_required
def stripe_payment_return(request):
    payment_intent_id = request.GET.get('payment_intent')
    payment_intent_client_secret = request.GET.get('payment_intent_client_secret')
    tx = get_object_or_404(MsgTx, stripe_payment_intent_id=payment_intent_id)
    payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
    if payment_intent['client_secret'] != payment_intent_client_secret:
        return redirect('proposals:msg_index')
    messages.success(request, gettext(
        'Fund migration successful. ' +
        'It may take a few seconds for the fund totals to update.'))
    return redirect(tx.msg.href())

@csrf_exempt
@require_http_methods(["POST"])
def stripe_webhook(request):
    event = None
    try:
        event = stripe.Webhook.construct_event(
            request.body,
            request.headers.get('Stripe-Signature'),
            settings.STRIPE_ENDPOINT_SECRET,
        )
    except ValueError as e:
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        return HttpResponse(status=400)

    if event.type == 'payment_intent.succeeded':
        payment_intent = event.data.object
        tx = get_object_or_404(MsgTx, stripe_payment_intent_id=payment_intent.id)
        tx.status = MsgTxStatus.SUCCEEDED.value
        tx.save()
    elif event.type == 'payment_intent.payment_failed':
        payment_intent = event.data.object
        tx = get_object_or_404(MsgTx, stripe_payment_intent_id=payment_intent.id)
        tx.status = MsgTxStatus.FAILED.value
        tx.save()

    # TODO Log these somewhere!
    return HttpResponse(status=200)

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def ajax(request):
    action_result = handle_msg_action(request)
    if isinstance(action_result, Msg):
        return HttpResponse(action_result.vote_total, status=200)
    elif isinstance(action_result, str):
        return redirect(action_result)

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q, F, Count, Sum, FloatField, ExpressionWrapper
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.html import escape
from django.utils.translation import gettext

import logging
import traceback
import pprint
pp = pprint.PrettyPrinter(width=100, compact=True)
from datetime import datetime
from difflib import HtmlDiff
from enum import Enum
from markdown import markdown
from markdown.extensions.toc import TocExtension, slugify
import math

from .helpers import get_object_or_None, get_display_rank, is_mod

def apply_sort_and_filter(all_msgs, user, sort_mode, filter_mode, has_rank=False):
    main_filter = Q(status__in=[
        MsgStatus.PENDING.value
            if is_mod(user) and not filter_mode['pending'] else None,
        MsgStatus.DECLINED.value
            if is_mod(user) and not filter_mode['declined'] else None,
        MsgStatus.ACTIVE.value if not filter_mode['active'] else None,
        MsgStatus.PAID.value if not filter_mode['paid'] else None,
        MsgStatus.FULFILLED.value if not filter_mode['fulfilled'] else None,
    ])
    if user.is_authenticated:
        main_filter = main_filter | Q(
            creator=user,
            status__in=[
                MsgStatus.PENDING.value if not filter_mode['pending'] else None,
                MsgStatus.DECLINED.value if not filter_mode['declined'] else None,
                MsgStatus.ACTIVE.value if not filter_mode['active'] else None,
                MsgStatus.PAID.value if not filter_mode['paid'] else None,
                MsgStatus.FULFILLED.value if not filter_mode['fulfilled'] else None,
            ],
        )
    all_results = all_msgs.filter(main_filter).filter(
        current_version=None,
    )
    if filter_mode['bids']:
        all_results = all_results.exclude(is_bid=True)
    if filter_mode['proposals']:
        all_results = all_results.exclude(is_proposal=True)
    if filter_mode['comments']:
        all_results = all_results.exclude(is_bid=False, is_proposal=False)
    if filter_mode['unmet_bids']:
        all_results = all_results.annotate(
            funds_remaining=ExpressionWrapper(
                Sum('tx__amount_cents') - (F('amount_threshold') * 100),
                output_field=FloatField(),
            ),
        ).filter(Q(funds_remaining__gte=0, is_bid=True) | Q(is_bid=False))
    if filter_mode['pending_edit']:
        all_results = all_results.exclude(has_pending_edit=False)

    if sort_mode == 'new':
        all_results = all_results.order_by('-created')
    elif sort_mode == 'top':
        all_results = all_results.order_by('-vote_total')
    elif sort_mode == 'hot' or not has_rank:
        all_results = all_results.annotate(
            display_rank=get_display_rank(),
        ).order_by('-display_rank')
    else:
        all_results = all_results.order_by('-rank')

    return all_results

class StripeConfig(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL,
        related_name='stripe',
        on_delete=models.CASCADE,
        blank=False,
        null=False)
    customer_id = models.CharField(max_length=255, blank=True, null=True)
    source_id = models.CharField(max_length=222, blank=True, null=True)
    card_id = models.CharField(max_length=255, blank=True, null=True)
    card_label = models.CharField(max_length=255, blank=True, null=True)
    connect_account = models.CharField(max_length=255, blank=True, null=True)
    connect_account_label = models.CharField(max_length=500, blank=True, null=True)

class MsgStatus(Enum):
    DRAFT = 0
    PENDING = 1
    ACTIVE = 2
    DECLINED = 3
    DELETED = 4
    PAID = 5
    FULFILLED = 6
    PREVIOUS_VERSION = 7

class MsgTxStatus(Enum):
    PENDING = 0
    SUCCEEDED = 1
    FAILED = 2
    CANCELLED = 3
    PAID_OUT = 4

class MsgNotificationKlass(Enum):
    NEW_REPLY = 0
    BID_PAID = 1
    BID_FULFILLED = 2
    USER_MENTION = 3

class MsgVote(models.Model):
    value = models.SmallIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL,
        related_name='msg_votes',
        on_delete=models.CASCADE)
    msg = models.ForeignKey('Msg',
        related_name='votes',
        on_delete=models.CASCADE)

class MsgTx(models.Model):
    amount_cents = models.IntegerField(blank=False, null=False)
    status = models.PositiveSmallIntegerField(
        default=MsgTxStatus.PENDING.value,
        choices=[(tag.value, tag.name) for tag in MsgTxStatus])
    created = models.DateTimeField(auto_now_add=True)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL,
        related_name='msg_tx',
        on_delete=models.SET_NULL,
        blank=True,
        null=True)
    msg = models.ForeignKey('Msg',
        related_name='tx',
        on_delete=models.SET_NULL,
        blank=True,
        null=True)
    stripe_payment_intent_id = models.CharField(
        max_length=255,
        unique=True,
        blank=True,
        null=True)
    next_tx = models.OneToOneField('MsgTx',
        related_name='prev_tx',
        on_delete=models.CASCADE, # in order to maintain consistency
        blank=True,
        null=True)

class MsgNotification(models.Model):
    msg = models.ForeignKey('Msg',
        related_name='notifications',
        on_delete=models.CASCADE,
        blank=True,
        null=True)
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL,
        related_name='notifications',
        on_delete=models.SET_NULL,
        blank=True,
        null=True)
    klass = models.PositiveSmallIntegerField(
        default=MsgNotificationKlass.NEW_REPLY.value,
        choices=[(tag.value, tag.name) for tag in MsgNotificationKlass])

    def new_reply(self):
        return self.klass == MsgNotificationKlass.NEW_REPLY.value
    def bid_paid(self):
        return self.klass == MsgNotificationKlass.BID_PAID.value
    def bid_fulfilled(self):
        return self.klass == MsgNotificationKlass.BID_FULFILLED.value
    def klass_class(self):
        if self.klass == MsgNotificationKlass.NEW_REPLY.value:
            return 'new-reply'
        if self.klass == MsgNotificationKlass.BID_PAID.value:
            return 'bid-paid'
        if self.klass == MsgNotificationKlass.BID_FULFILLED.value:
            return 'bid-fulfilled'

class Msg(models.Model):
    parent = models.ForeignKey('Msg', related_name='children',
        on_delete=models.CASCADE, blank=True, null=True)
    path = ArrayField(models.PositiveIntegerField(), blank=True, null=True)
    title = models.CharField(max_length=200)
    text = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL,
        related_name='msg',
        on_delete=models.SET_NULL, null=True, blank=True)
    collaborators = models.ManyToManyField(settings.AUTH_USER_MODEL,
        related_name='collab_access')
    collab_str = models.CharField(max_length=1000, default='')
    updated = models.DateTimeField(auto_now_add=True)
    current_version = models.ForeignKey('Msg', related_name='previous_versions',
        on_delete=models.CASCADE, blank=True, null=True)
    update_creator = models.ForeignKey(settings.AUTH_USER_MODEL,
        related_name='msg_updates',
        on_delete=models.SET_NULL, null=True, blank=True)
    status = models.PositiveSmallIntegerField(
        default=MsgStatus.PENDING.value,
        choices=[(tag.value, tag.name) for tag in MsgStatus])
    has_pending_edit = models.BooleanField(default=False)
    vote_score = models.FloatField(default=0)
    vote_total = models.IntegerField(default=0)
    vote_positive = models.PositiveIntegerField(default=0)
    vote_negative = models.PositiveIntegerField(default=0)
    is_proposal = models.BooleanField(default=False)
    is_bid = models.BooleanField(default=False)
    amount_threshold = models.PositiveIntegerField(default=settings.MIN_BID,
        null=True, blank=True) # in dollars
    expiration = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = 'Proposals'
        ordering = ['created']

    def __str__(self):
        return '%s - %s' % (self.pk, self.title)

    def draft(self):
        return self.status == MsgStatus.DRAFT.value
    def pending(self):
        return self.status == MsgStatus.PENDING.value
    def active(self):
        return self.status == MsgStatus.ACTIVE.value
    def declined(self):
        return self.status == MsgStatus.DECLINED.value
    def deleted(self):
        return self.status == MsgStatus.DELETED.value
    def paid(self):
        return self.status == MsgStatus.PAID.value
    def fulfilled(self):
        return self.status == MsgStatus.FULFILLED.value

    def my_vote(self, user):
        if not user.is_authenticated:
            return 0
        return (get_object_or_None(MsgVote, msg=self, creator=user) \
                or MsgVote(value=0)).value

    def set_my_vote(self, user, value):
        if not user.is_authenticated:
            raise ValueError('invalid_user')
        if not self.visible_for_me(user):
            raise ValueError('unauthorized')
        value = int(value)
        if value < -1 or value > 1:
            raise ValueError('value_mismatch')
        vote, _ = MsgVote.objects.get_or_create(creator=user,msg=self)
        vote.value = value
        vote.save()

        # update denormalized aggregates on Msg
        positive = self.votes.filter(value=1) \
            .aggregate(count=Count('*'))['count'] or 0
        negative = self.votes.filter(value=-1) \
            .aggregate(count=Count('*'))['count'] or 0
        self.vote_positive = positive
        self.vote_negative = negative
        self.vote_total = positive - negative

        calc_score = None
        negative *= -1
        if positive + negative < 0:
            positive,negative = negative,positive
        elif positive + negative == 0:
            calc_score = 0

        if calc_score is None:
            # From http://www.evanmiller.org/how-not-to-sort-by-average-rating.html
            calc_score = ((positive + 1.9208) / (positive + negative) - \
               1.96 * math.sqrt((positive * negative) / (positive + negative) + 0.9604) / \
                  (positive + negative)) / (1 + 3.8416 / (positive + negative))

        self.vote_score = calc_score
        self.save(update_fields=[
            'vote_score',
            'vote_positive',
            'vote_negative',
            'vote_total',
        ])

    def is_collaborator(self, user):
        if not user.is_authenticated:
            return False
        if self.creator == user:
            return True
        return user.collab_access.filter(pk=self.pk).exists()

    def collaborator_list_str(self):
        if self.id:
            return ', '.join(list(map(lambda c: c.username, self.collaborators.all())))
        return ''

    def active_collabs(self):
        result = [ self.creator ]
        for version in self.previous_versions.all():
            if version.update_creator not in result:
                result.append(version.update_creator)
        return result

    def parent_id_or_empty_str(self):
        if not self.parent:
            return ''
        return self.parent.pk

    def ancestors(self, include_funds_personal_user=False, refresh=False):
        if not refresh and self.path:
            result = list(map(lambda pk: Msg.objects.get(pk=pk), self.path))
            if include_funds_personal_user:
                for msg in result:
                    msg.funds_personal = msg.funds_collected_personal(
                        include_funds_personal_user)
            return result

        # Determine path manually
        result = []
        msg = self
        while msg.parent:
            msg = msg.parent
            if include_funds_personal_user:
                msg.funds_personal = msg.funds_collected_personal(
                    include_funds_personal_user)
            result.append(msg)
        result.reverse()
        return result

    def update_descendent_paths(self):
        for child in self.children.all():
            child.path = list(map(lambda m: m.pk, child.ancestors(False, True)))
            child.save(update_fields=['path'])
            child.update_descendent_paths()

    def text_html(self):
        # TODO where are my blockquotes at?
        return markdown(escape(self.text),
            output_format="html5",
            extensions=[
                'nl2br',
                'tables',
                TocExtension(
                    baselevel=2,
                    slugify=lambda value,sep:
                        str(self.pk) + sep + slugify(value,sep),
                ),
            ])

    def visible_for_me(self, user):
        if self.status in [
                MsgStatus.DRAFT.value,
                MsgStatus.PENDING.value,
                MsgStatus.DECLINED.value,
            ] and not (self.is_collaborator(user) or is_mod(user)):
            return False
        if self.status == MsgStatus.PREVIOUS_VERSION.value:
            return False
        return True

    def pending_edit(self):
        latest_version = self.previous_versions.order_by('-pk').first()
        if latest_version and latest_version.pending():
            return latest_version
        return None

    def diff(self, other, full_diff):
        out = HtmlDiff().make_table(
            self.title.splitlines(keepends=True),
            other.title.splitlines(keepends=True),
            gettext('Current Title'),
            gettext('Pending Title'),
        ) + HtmlDiff().make_table(
            self.text.splitlines(keepends=True),
            other.text.splitlines(keepends=True),
            gettext('Current Text'),
            gettext('Pending Text'),
        )
        if full_diff:
            out += HtmlDiff().make_table(
                [ 'Collaborators: ' + (self.collab_str or ''),
                    'Is Proposal: ' + ('Yes' if self.is_proposal else 'No'),
                    'Is Bid: ' + ('Yes' if self.is_bid else 'No'),
                    'Threshold Amount: ' + str(self.amount_threshold),
                    'Expiration: ' + str(self.expiration) ],
                [ 'Collaborators: ' + (other.collab_str or ''),
                    'Is Proposal: ' + ('Yes' if other.is_proposal else 'No'),
                    'Is Bid: ' + ('Yes' if other.is_bid else 'No'),
                    'Threshold Amount: ' + str(other.amount_threshold),
                    'Expiration: ' + str(other.expiration) ],
                gettext('Current Values'),
                gettext('Pending Values'),
            )
        return out

    def href(self):
        if self.current_version:
            root_pk = self.current_version.pk
        else:
            root_pk = self.pk

        return reverse('proposals:msg_index', kwargs={
            'root': root_pk
        })

    def children_sorted(self, sort_mode, user, filter_mode):
        return apply_sort_and_filter(
            self.children, user, sort_mode, filter_mode, False)

    def funds_collected_personal(self, user):
        if not user.is_authenticated:
            return 0
        return self.tx.filter(
            creator=user,
            status=MsgTxStatus.SUCCEEDED.value,
        ).aggregate(sum=Sum('amount_cents'))['sum'] or 0
    def funds_collected_all(self):
        return self.tx.filter(
            status=MsgTxStatus.SUCCEEDED.value,
        ).aggregate(sum=Sum('amount_cents'))['sum'] or 0

    def bid_remaining(self):
        return (self.amount_threshold * 100) - self.funds_collected_all()
    def bid_expired(self):
        return self.is_bid and self.expiration < datetime.now()
    def bid_pending_payout(self):
        return self.is_bid \
            and self.status == MsgStatus.ACTIVE.value \
            and self.creator.stripe.connect_account \
            and self.bid_remaining() < 0 \
            and self.bid_expired()

    def can_update_full(self, user):
        return self.creator == user or is_mod(user)
    def can_update(self, user):
        return self.can_update_full(user) or self.is_collaborator(user)

    def set_status(self, new_status):
        if new_status == self.status:
            return False
        self.status = new_status
        self.save(update_fields=['status'])
        if new_status == MsgStatus.ACTIVE.value:
            if self.parent:
                notif = MsgNotification(
                    msg=self,
                    recipient=self.parent.creator,
                    klass=MsgNotificationKlass.NEW_REPLY.value,
                )
                notif.save()
        elif new_status == MsgStatus.PAID.value:
            notif = MsgNotification(
                msg=self,
                recipient=self.creator,
                klass=MsgNotificationKlass.BID_PAID.value,
            )
            notif.save()
        elif new_status == MsgStatus.FULFILLED.value:
            notif = MsgNotification(
                msg=self,
                recipient=self.creator,
                klass=MsgNotificationKlass.BID_FULFILLED.value,
            )
            notif.save()

    def update_collabs(self, ignore_username):
        collab_usernames = list(filter(
            lambda name: not(name == '' or name == ignore_username),
            map(str.strip, self.collab_str.split(','))))

        if not len(collab_usernames):
            collab_users = []
        else:
            collab_users = User.objects.filter(username__in=collab_usernames)

        all_collabs = self.collaborators.all()
        for existing_collab_user in all_collabs:
            if not existing_collab_user in collab_users:
                self.collaborators.remove(existing_collab_user)
        for collab_user in collab_users:
            if not collab_user in all_collabs:
                self.collaborators.add(collab_user)

    def approve_edit(self, request):
        if not is_mod(request.user):
            messages.error(request, gettext('Unauthorized'))
        elif not self.has_pending_edit:
            messages.error(request, gettext('Invalid action'))
        else:
            pending_edit = self.pending_edit()
            if not pending_edit:
                messages.error(request, gettext('Invalid Action'))
                return
            self.title = pending_edit.title
            self.text = pending_edit.text
            self.collab_str = pending_edit.collab_str
            self.is_proposal = pending_edit.is_proposal
            self.is_bid = pending_edit.is_bid
            self.amount_threshold = pending_edit.amount_threshold
            self.expiration = pending_edit.expiration
            self.updated = pending_edit.updated
            self.has_pending_edit = False

            self.save()
            self.update_collabs(request.user.username)
            pending_edit.delete()

    def post_update(self, request):
        if self.status == MsgStatus.PREVIOUS_VERSION.value:
            messages.error(request, gettext('Cannot edit previous versions'))
            return False
        if not self.can_update(request.user):
            messages.error(request, gettext('Unauthorized to update this post'))
            return False

        is_creation = False if self.pk else True
        if not is_creation:
            prev_version = get_object_or_404(Msg, pk=self.pk)
            prev_version.pk = None

        success = True
        new_parent = False

        if is_mod(request):
            new_status = request.POST.get('status')
            if new_status:
                self.status = new_status
            parent_id = request.POST.get('parent')
            if not parent_id:
                parent = None
            else:
                parent = get_object_or_404(Msg, pk=parent_id)
                if is_creation or parent.pk != self.parent.pk:
                    new_parent = True

        if self.can_update_full(request.user):
            is_bid = request.POST.get('is_bid') == 'true'

            expiration_date = request.POST.get('expiration_date')
            expiration_time = request.POST.get('expiration_time') or '00:00'
            expiration = None
            if is_bid:
                if not expiration_date or not expiration_time:
                    success = False
                    messages.error(request, gettext('Invalid expiration date/time'))
                else:
                    try:
                        expiration = datetime.strptime(
                            expiration_date + 'T' + expiration_time,
                            '%Y-%m-%dT%H:%M')
                    except:
                        success = False
                        messages.error(request, gettext('Invalid expiration date/time'))

            collab_input = request.POST.get('collaborators')
            collab_usernames = list(set(filter(
                lambda name: not(name == '' or name == request.user.username),
                map(str.strip, collab_input.split(',')))))
            if len(collab_usernames):
                collab_users = User.objects.filter(username__in=collab_usernames)
                self.collab_str = ', '.join(list(map(lambda c: c.username, collab_users)))
                if len(collab_users) != len(collab_usernames):
                    missing_usernames = filter(
                        lambda username:
                            not collab_users.filter(username=username).exists(),
                        collab_usernames)
                    messages.error(request, gettext(
                        'Invalid usernames for collaboration: %s')
                            % ', '.join(missing_usernames))
                    success = False
            else:
                self.collab_str = ''

            if new_parent:
                self.parent = parent
                self.path = list(map(lambda m: m.pk, parent.ancestors())) + [parent.pk] \
                    if parent else None
            self.is_proposal = request.POST.get('is_proposal') == 'true'
            if not (self.paid() or self.fulfilled()):
                self.is_bid = is_bid
                self.amount_threshold = request.POST.get('amount_threshold') or None
                self.expiration = expiration

        # Fields that collaborators can edit
        self.title = request.POST.get('title')
        self.text = request.POST.get('text')
        self.updated = datetime.now()

        if success:
            try:
                if is_creation:
                    self.save()
                    self.update_collabs(request.user.username)
                    return True

                canonical_parent = get_object_or_404(Msg, pk=self.pk)
                if new_parent:
                    self.update_descendent_paths()
                prev_version.status = MsgStatus.PREVIOUS_VERSION.value
                prev_version.current_version = canonical_parent
                prev_version.update_creator = request.user
                prev_version.created = datetime.now()
                prev_version.save()
                if not is_mod(request):
                    canonical_parent.has_pending_edit = True
                    self.pk = None
                    self.status = MsgStatus.PENDING.value
                    self.current_version = canonical_parent
                    self.update_creator = request.user
                else:
                    self.has_pending_edit = False
                    self.update_collabs(request.user.username)
                self.save()
                if self.pk != canonical_parent.pk:
                    canonical_parent.save(update_fields=['has_pending_edit'])
            except Exception as e:
                logging.error(traceback.format_exc())
                success = False
                messages.error(request, gettext('Unknown error saving post'))
        return success

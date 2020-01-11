from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.db.models import Sum
from django.conf import settings
from django.contrib import messages
from django.utils.translation import gettext

import pprint
pp = pprint.PrettyPrinter(width=100, compact=True)
import stripe

from .models2 import MsgStatus, MsgTxStatus, MsgTx, MsgVote, Msg, StripeConfig
from .forms import SignUpForm, AddCardForm
from .helpers import get_all_funded_msg

def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            form.save()
            username = form.cleaned_data.get('username')
            raw_password = form.cleaned_data.get('password1')
            user = authenticate(username=username, password=raw_password)
            if user.pk == 1:
                # First user is automatically a moderator
                moderator_group, _ = Group.objects.get_or_create(name='moderator')
                user.groups.add(moderator_group)
            login(request, user)
            return redirect('proposals:index')
    else:
        form = SignUpForm()
    return render(request, 'registration/signup.html', {'form': form})

@login_required
def profile(request):
    return render(request, 'profile/index.html', {
        'card_label':  request.user.stripe.card_label
            if hasattr(request.user, 'stripe') else None,
        'connect_account_label':  request.user.stripe.connect_account_label
            if hasattr(request.user, 'stripe') else None,
        'stripe_connect_uri': 'https://connect.stripe.com/oauth/authorize?' + \
            'response_type=code&client_id=%s&scope=read_write&redirect_uri=%s' \
            % (
                settings.STRIPE_CONNECT_CLIENT_ID,
                settings.STRIPE_CONNECT_REDIRECT_URI
            ),
        'uncommitted_funds_amount': request.user.msg_tx.filter(
                status=MsgTxStatus.SUCCEEDED.value,
                msg__status__in=[
                    MsgStatus.ACTIVE.value,
                    MsgStatus.PENDING.value,
                    MsgStatus.DECLINED.value,
                ],
            ).aggregate(sum=Sum('amount_cents'))['sum'] or 0,
    })

@login_required
def payment_method(request):
    if request.method == 'POST':
        form = AddCardForm(request.POST)
        if form.is_valid():
            seti_id = form.cleaned_data.get('seti_id')
            payment_method_id = form.cleaned_data.get('payment_method_id')
            payment_method = stripe.PaymentMethod.retrieve(payment_method_id)
            card_label = gettext(
                '%(brand)s ending in %(last4)s, exp. %(exp_month)s/%(exp_year)s') % {
                    'brand': payment_method['card']['brand'],
                    'last4': payment_method['card']['last4'],
                    'exp_month': payment_method['card']['exp_month'],
                    'exp_year': payment_method['card']['exp_year'],
                }
            if hasattr(request.user, 'stripe'):
                old_payment_method = stripe.PaymentMethod.retrieve(
                    request.user.stripe.card_id
                )
                if request.user.stripe.card_id \
                        and old_payment_method['customer'] is not None:
                    stripe.PaymentMethod.detach(request.user.stripe.card_id)
                request.user.stripe.card_id=payment_method_id
                request.user.stripe.card_label=card_label
                request.user.stripe.save()
                if request.user.stripe.customer_id:
                    stripe.PaymentMethod.attach(
                        payment_method_id,
                        customer=request.user.stripe.customer_id
                    )
            else:
                customer = stripe.Customer.create(
                    email=request.user.email,
                    description=request.user.id,
                )
                stripe.PaymentMethod.attach(
                    payment_method_id,
                    customer=customer.id
                )
                stripe_config = StripeConfig(
                    user=request.user,
                    card_id=payment_method_id,
                    card_label=card_label,
                    customer_id=customer.id,
                )
                stripe_config.save()
            messages.success(request, gettext('Successfully added %(card_label)s') % {
                'card_label': card_label
            })
        else:
            messages.error(request, gettext(
                'Unable to set payment method, please try again.'))
        next_uri = request.POST.get('next')
        if next_uri:
            return redirect(next_uri)
        return redirect('proposals:profile')
    return render(request, 'profile/payment_method.html', {
        'next': request.GET.get('next') or None,
        'card_id':  request.user.stripe.card_id
            if hasattr(request.user, 'stripe') else None,
        'client_secret': stripe.SetupIntent.create().client_secret,
        'card_label':  request.user.stripe.card_label
            if hasattr(request.user, 'stripe') else None,
    })

@login_required
def funds(request):
    if request.method == 'POST':
        refund_txs = []
        total = 0
        for field_name, field_value in request.POST.items():
            # Migrate funds from other funds
            if field_name[:4] == 'msg_':
                refund_from_id = int(field_name[4:])
                refund_amount = float(field_value)
                refund_amount_cents = int(refund_amount * 100)
                refund_from = get_object_or_404(Msg, pk=refund_from_id)
                refund_from_available = \
                    refund_from.funds_collected_personal(request.user)

                if refund_amount_cents > refund_from_available:
                    messages.error(request, gettext(
                        'Insufficient amount available.'))
                    return redirect(request.get_full_path())
                if refund_from.bid_expired() \
                        and refund_from.bid_remaining() < 0:
                    messages.error(request, gettext(
                        'Cannot refund bid after its expiration ' + \
                        'over the threshold amount.'))
                    return redirect(request.get_full_path())
                if refund_from.paid() or refund_from.fulfilled():
                    messages.error(request, gettext(
                        'Cannot refund bid after payment to bidder.'))
                    return redirect(request.get_full_path())

                refund_tx = MsgTx(
                    creator=request.user,
                    msg=refund_from,
                    amount_cents=-refund_amount_cents,
                    status=MsgTxStatus.SUCCEEDED.value,
                )
                refund_tx.save()
                refund_txs.append(refund_tx)
                total += refund_amount_cents
        if total == 0:
            messages.error(request, gettext('No refund specified'))
            return redirect(request.get_full_path())
        card_payments = request.user.msg_tx.filter(
            status=MsgTxStatus.SUCCEEDED.value,
        ).exclude(
            stripe_payment_intent_id=None,
        ).order_by('-created')
        amount_remaining = total
        for payment in card_payments:
            payment_intent = stripe.PaymentIntent.retrieve(
                payment.stripe_payment_intent_id,
            )
            for charge in payment_intent.charges.data:
                charge_max_refund = \
                    round(charge.amount * settings.REFUND_PROPORTION) \
                        - charge.amount_refunded
                if charge_max_refund <= 0:
                    continue
                elif amount_remaining > charge_max_refund:
                    # Will need to spill into other payments
                    new_refund_amount = charge_max_refund
                else:
                    new_refund_amount = amount_remaining
                if new_refund_amount > 0:
                    amount_remaining -= new_refund_amount
                    refund = stripe.Refund.create(
                        charge=charge.id,
                        amount=new_refund_amount,
                        reason='requested_by_customer')

                    if refund.status == 'failed':
                        messages.error(request, gettext(
                            'Unable to refund payment, please try again or contact us.'))
                        return redirect(proposal.href())
        if amount_remaining == 0:
            messages.success(request, gettext('Refund initiated successfully.'))
            return redirect('proposals:profile')
        else:
            messages.error(request, gettext(
                'Unknown error with refund. Please contact us.'))
    all_funds = get_all_funded_msg(request.user)
    return render(request, 'profile/refund.html', {
        'funded_msg': all_funds,
    })

@login_required
def stripe_connect_return(request):
    token_response = stripe.OAuth.token(
        grant_type='authorization_code',
        code=request.GET.get('code', ''),
    )
    if 'stripe_user_id' in token_response:
        account_details = stripe.Account.retrieve(token_response['stripe_user_id'])
        account_label = "%s (%s)" % (
            account_details.settings.dashboard.display_name,
            account_details.email,
        )
        if hasattr(request.user, 'stripe'):
            request.user.stripe.connect_account = token_response['stripe_user_id']
            request.user.stripe.connect_account_label = account_label
            request.user.stripe.save()
        else:
            stripe_config = StripeConfig(
                user=request.user,
                connect_account=token_response['stripe_user_id'],
                connect_account_label=account_label
            )
            stripe_config.save()
        messages.success(request, gettext(
            'Successfully linked Stripe account %(account_label)s') % {
                'account_label': account_label
            })
    return redirect('proposals:profile')

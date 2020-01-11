from django.conf import settings

from .helpers import is_mod

def base_constants(request):
    return {
        'STRIPE_PUBLISHABLE_KEY': settings.STRIPE_PUBLISHABLE_KEY,
        'ENABLE_CROWDFUNDING': settings.ENABLE_CROWDFUNDING,
        'ROOT_POST_ID': settings.ROOT_POST_ID,
        'MIN_BID': settings.MIN_BID,
        'MAX_BID': settings.MAX_BID,
        'MIN_FUND': settings.MIN_FUND,
        'MAX_FUND': settings.MAX_FUND,
        'REFUND_PROPORTION': settings.REFUND_PROPORTION,
        'PAYOUT_PROPORTION': settings.PAYOUT_PROPORTION,
        'lang_code': request.LANGUAGE_CODE,
        'is_moderator': is_mod(request),
    }

from django.urls import path

from . import views2, profile_views

app_name = 'proposals'
# TODO i18n for urls too!
urlpatterns = [
    path('', views2.msg_home, name='index'),
    path('<int:root>', views2.msg_index, name='msg_index'),
    path('create-post', views2.msg_create, name='msg_create'),
    path('edit-post', views2.msg_edit, name='msg_edit'),
    path('search', views2.msg_search, name='msg_search'),
    path('ajax', views2.ajax, name='ajax'),
    path('<int:msg_id>/add-fund', views2.msg_fund, name='msg_fund'),
    path('join', profile_views.signup, name='signup'),
    path('notifications', views2.msg_notifications, name='notifications'),
    path('profile/', profile_views.profile, name='profile'),
    path('profile/payment-method', profile_views.payment_method, name='profile_payment_method'),
    path('profile/funds', profile_views.funds, name='profile_funds'),
    path('stripe-connect-return', profile_views.stripe_connect_return, name='stripe_connect_return'),
    path('stripe-payment-return', views2.stripe_payment_return, name='stripe_payment_return'),
    path('stripe-webhook', views2.stripe_webhook, name='stripe_webhook'),
    path('u/<str:username>', views2.msg_user_detail, name='user_detail'),
]

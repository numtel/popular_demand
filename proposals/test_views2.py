from django.contrib.auth.models import Group, User
from django.test import TestCase, Client

import pprint
pp = pprint.PrettyPrinter(width=100, compact=True)
from datetime import datetime

from .models2 import MsgStatus, MsgTxStatus, MsgTx, MsgVote, Msg, StripeConfig

def edit_case(self, case):
    cli = Client()
    if 'user' in case:
        cli.force_login(case['user'])
    response = cli.get('/en/edit-post', {'msg': case['msg'].pk})
    if 'redirect' in case:
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, case['redirect'])
    else:
        self.assertEqual(response.context['msg'], case['msg'])
        self.assertEqual(response.context['parent'], case['msg'].parent)

        response = cli.post(
            '/en/edit-post?msg=' + str(case['msg'].pk), case['post_body'])
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/en/' + str(case['msg'].pk))

        response = cli.get(response.url)
        compare_msg = response.context['root']
        self.assertEqual(compare_msg.collaborators.count(), case['collab_count'])
        self.assertEqual(len(response.context['msgs']), case['child_count'])

        if not case['user'].groups.filter(name=self.mod_group).exists():
            compare_msg = compare_msg.pending_edit()
            self.assertEqual(compare_msg.status, MsgStatus.PENDING.value)
            self.assertEqual(compare_msg.current_version.pk, case['msg'].pk)
            self.assertEqual(compare_msg.update_creator, case['user'])
            # Non-moderator cannot change parent
            if 'parent' in case['post_body']:
                self.assertEqual(compare_msg.parent, case['msg'].parent)
        else:
            # Moderator-only parent change
            if 'parent' in case['post_body']:
                if case['post_body']['parent'] == '':
                    self.assertEqual(compare_msg.parent, case['msg'].parent)
                else:
                    self.assertEqual(compare_msg.parent.pk, int(case['post_body']['parent']))
        if 'expected_path' in case:
            self.assertEqual(len(compare_msg.path), len(case['expected_path']))
            for index, elem in enumerate(case['expected_path']):
                self.assertEqual(compare_msg.path[index], elem.pk)
        if 'collab_str' in case:
            self.assertEqual(compare_msg.collab_str, case['collab_str'])
        self.assertEqual(compare_msg.title, case['post_body']['title'])
        self.assertEqual(compare_msg.text, case['post_body']['text'])

class MsgViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user1 = User.objects.create_user('test1')
        cls.mod_group, _ = Group.objects.get_or_create(name='moderator')
        cls.mod_user1 = User.objects.create_user('test_mod1')
        cls.mod_group.user_set.add(cls.mod_user1)

        cls.root = Msg(
            title='test_root',
            text='test_text1',
            creator=cls.mod_user1,
            status=MsgStatus.ACTIVE.value,
        )
        cls.root.save()

        cls.msg1 = Msg(
            title='test_msg1',
            text='test_text_msg1',
            creator=cls.user1,
            parent=cls.root,
            status=MsgStatus.ACTIVE.value,
        )
        cls.msg1.save()
        cls.msg2 = Msg(
            title='test_msg2',
            text='test_text_msg2',
            creator=cls.user1,
            parent=cls.root,
            status=MsgStatus.ACTIVE.value,
        )
        cls.msg2.save()

    def testGetHome(self):
        cli = Client()
        response = cli.get('/en/')
        self.assertEqual(
            response.context['title'][:len(self.root.title)],
            self.root.title)
        self.assertEqual(response.context['root'], self.root)
        self.assertEqual(len(response.context['msgs']), 2)

    def testCreateSimpleAsMod(self):
        post_body = {
            'title': 'insert me',
            'text': 'goes here',
            'collaborators': '',
        }
        cli = Client()
        cli.force_login(self.mod_user1)
        response = cli.post('/en/create-post?parent=' + str(self.root.pk), post_body)
        self.assertEqual(response.status_code, 302)

        response = cli.get(response.url)
        self.assertEqual(response.context['root'].title, post_body['title'])
        self.assertEqual(response.context['root'].text, post_body['text'])
        self.assertEqual(response.context['root'].status, MsgStatus.PENDING.value)

    def testEditRootLoggedOut(self):
        edit_case(self, {
            'msg': self.root,
            'redirect': '/accounts/login/?next=/en/edit-post%3Fmsg%3D' + str(self.root.pk),
        })

    def testEditChildLoggedOut(self):
        edit_case(self, {
            'msg': self.msg1,
            'redirect': '/accounts/login/?next=/en/edit-post%3Fmsg%3D' + str(self.msg1.pk),
        })

    def testEditChildLoggedIn(self):
        edit_case(self, {
            'user': self.user1,
            'msg': self.msg1,
            'post_body': {
                'title': 'newtitle',
                'text': 'newtext',
                'collaborators': '',
            },
            'collab_count': 0,
            'child_count': 0,
        })

    def testEditChildCollabsLoggedIn(self):
        edit_case(self, {
            # This edit will be moderated
            'user': self.user1,
            'msg': self.msg1,
            'post_body': {
                'title': 'newtitle2',
                'text': 'newtext2',
                'collaborators': self.mod_user1.username \
                    + ',,' + self.mod_user1.username \
                    + ', ' + self.user1.username,
            },
            # Creator user is stripped from the collab_str
            'collab_str': self.mod_user1.username,
            # Actual collab foreign keys only updated after edit approved
            'collab_count': 0,
            'child_count': 0,
        })

    def testEditRootLoggedIn(self):
        edit_case(self, {
            'user': self.user1,
            'msg': self.root,
            'redirect': '/en/',
        })

    def testEditRootMod(self):
        edit_case(self, {
            'user': self.mod_user1,
            'msg': self.root,
            'post_body': {
                'title': 'newroottitle',
                'text': 'newroottext',
                'collaborators': '',
            },
            'collab_count': 0,
            'child_count': 2,
        })

    def testEditRootCollabMod(self):
        edit_case(self, {
            'user': self.mod_user1,
            'msg': self.root,
            'post_body': {
                'title': 'newroottitle',
                'text': 'newroottext',
                'collaborators': self.user1.username,
            },
            'collab_count': 1,
            'child_count': 2,
        })

    def testEditNewParentLoggedIn(self):
        edit_case(self, {
            'user': self.user1,
            'msg': self.msg1,
            'post_body': {
                'title': 'new124ttitle',
                'text': 'new1234text',
                'collaborators': '',
                'parent': str(self.msg2.pk) # will have no effect
            },
            'collab_count': 0,
            'child_count': 0,
        })

    def testEditNewParentMod(self):
        edit_case(self, {
            'user': self.mod_user1,
            'msg': self.msg1,
            'post_body': {
                'title': 'new124ttitle',
                'text': 'new1234text',
                'collaborators': '',
                'parent': str(self.msg2.pk)
            },
            'expected_path': [ self.root, self.msg2 ],
            'collab_count': 0,
            'child_count': 0,
        })

    def testEditEmptyParentMod(self):
        edit_case(self, {
            'user': self.mod_user1,
            'msg': self.msg1,
            'post_body': {
                'title': 'new2345title',
                'text': 'new2345text',
                'collaborators': '',
                'parent': '', # will not move
            },
            'collab_count': 0,
            'child_count': 0,
        })


    # TODO test payment method add
    # test funding from cc -- requires selenium test
    # test front end migrate/refund table lists parent/all funded proposals and active bids not expired and over threshold
    def testPaymentMethodRedirectFromFund(self):
        cli = Client()
        cli.force_login(self.user1)
        prop1 = Msg(
            title='test_msg1',
            text='test_text_msg1',
            creator=self.user1,
            parent=self.root,
            status=MsgStatus.ACTIVE.value,
            is_proposal=True,
        )
        prop1.save()
        response = cli.get('/en/%s/add-fund' % prop1.pk, {})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url,
            '/en/profile/payment-method?next=%2Fen%2F' + str(prop1.pk) + '%2Fadd-fund')

    def testFund(self):
        cli = Client()
        cli.force_login(self.user1)
        stripe_config = StripeConfig(
            user=self.user1,
            customer_id='fake123',
            card_id='fake123',
            card_label='fake123',
        )
        stripe_config.save()
        prop1 = Msg(
            title='test_msg1',
            text='test_text_msg1',
            creator=self.user1,
            parent=self.root,
            status=MsgStatus.ACTIVE.value,
            is_proposal=True,
        )
        prop1.save()
        prop1_bid1 = Msg(
            title='test_msg1',
            text='test_text_msg1',
            creator=self.user1,
            parent=prop1,
            status=MsgStatus.ACTIVE.value,
            is_bid=True,
            amount_threshold=10,
            expiration=datetime(2018,11,30), # in the past (expired)
        )
        prop1_bid1.save()
        fund_prop1 = MsgTx(
            amount_cents=3400,
            status=MsgTxStatus.SUCCEEDED.value,
            creator=self.user1,
            msg=prop1,
            stripe_payment_intent_id='fake123',
        )
        fund_prop1.save()
        response = cli.get('/en/%s/add-fund' % prop1_bid1.pk, {})
        self.assertEqual(response.context['msg'], prop1_bid1)
        self.assertEqual(response.context['card_label'], stripe_config.card_label)
        # Does not include the root msg since it doesn't have any personal funds
        self.assertEqual(len(response.context['funded_msg']), 1)
        self.assertEqual(response.context['funded_msg'][0].pk, prop1.pk)


    # test moving from active proposal to child/sibling proposal/bid
    # test moving from active bid before/after expiration above/below threshold
    # test refund from active/paid/fulfilled propsal/bid

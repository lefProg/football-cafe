from django.conf import settings
from django.test import override_settings
from django.urls import reverse

from core.enums import VoteChoice
from core.models import Vote

from .base import CafeBase

AGREE, DISAGREE = VoteChoice.AGREE, VoteChoice.DISAGREE


class VotingTests(CafeBase):
    def setUp(self):
        super().setUp()
        self.article = self.make_article(claims=2)
        self.first, self.second = self.article.claims.all()

    def vote(self, position, choice):
        return self.client.post(reverse('claim-vote', args=[self.article.slug, position]), {'choice': choice})

    def test_first_tick_saves_the_vote_and_hands_out_a_visitor_cookie(self):
        response = self.vote(1, AGREE)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                'claim': {
                    'position': 1,
                    'text': 'Claim number 1.',
                    'my_choice': AGREE,
                    'percent_agree': 100,
                    'vote_count': 1,
                },
                'coupon': {'ticked': 1, 'total': 2, 'verdict': ''},
            },
        )
        self.assertIn(settings.CAFE_VISITOR_COOKIE, response.cookies)
        self.assertTrue(response.cookies[settings.CAFE_VISITOR_COOKIE]['httponly'])
        self.assertEqual(Vote.objects.get().choice, AGREE)

    def test_the_cookie_works_on_plain_http_and_is_https_only_when_the_site_is(self):
        self.assertFalse(self.vote(1, AGREE).cookies[settings.CAFE_VISITOR_COOKIE]['secure'])
        with override_settings(HTTPS=True):
            self.assertTrue(self.vote(1, AGREE).cookies[settings.CAFE_VISITOR_COOKIE]['secure'])

    def test_changing_your_mind_replaces_the_vote(self):
        self.vote(1, AGREE)
        response = self.vote(1, DISAGREE)
        self.assertEqual(response.json()['claim']['percent_agree'], 0)
        self.assertEqual(Vote.objects.count(), 1)

    def test_percentage_counts_everyone(self):
        for choice in (AGREE, AGREE, DISAGREE):
            self.make_vote(self.first, choice)
        claim = self.vote(1, DISAGREE).json()['claim']
        self.assertEqual((claim['percent_agree'], claim['vote_count']), (50, 4))

    def test_a_full_coupon_gets_a_verdict(self):
        self.make_vote(self.second, AGREE)
        self.vote(1, AGREE)
        response = self.vote(2, DISAGREE)
        self.assertEqual(
            response.json()['coupon'],
            {
                'ticked': 2,
                'total': 2,
                'verdict': 'You are with the house on 1 of 2. The cafe is most divided on claim 2: 50% agree.',
            },
        )

    def test_bad_requests_are_refused(self):
        self.assertEqual(self.vote(1, 3).json(), {'choice': ['"3" is not a valid choice.']})
        self.assertEqual(self.vote(1, 3).status_code, 400)
        self.assertEqual(self.client.post(reverse('claim-vote', args=[self.article.slug, 1]), {}).status_code, 400)
        self.assertEqual(self.vote(9, AGREE).status_code, 404)
        self.assertEqual(self.client.get(reverse('claim-vote', args=[self.article.slug, 1])).status_code, 405)
        self.assertEqual(Vote.objects.count(), 0)

    def test_a_forged_cookie_is_treated_as_a_new_reader(self):
        self.client.cookies[settings.CAFE_VISITOR_COOKIE] = 'not-a-signed-value'
        self.assertEqual(self.vote(1, AGREE).status_code, 200)

    def test_drafts_cannot_be_voted_on(self):
        draft = self.make_article(slug='draft', published=False)
        response = self.client.post(reverse('claim-vote', args=[draft.slug, 1]), {'choice': AGREE})
        self.assertEqual(response.status_code, 404)

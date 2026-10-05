from django.contrib.auth import get_user_model
from django.urls import reverse

from core.enums import ReplyStatus, VoteChoice
from core.models import Argument

from .base import CafeBase


class EmptyCafeTests(CafeBase):
    def test_home_says_the_first_piece_is_coming(self):
        self.assertContains(self.client.get(reverse('home')), 'The first piece is on its way')

    def test_past_rounds_and_house_rules_load(self):
        self.assertEqual(self.client.get(reverse('past_rounds')).status_code, 200)
        self.assertContains(self.client.get(reverse('house_rules')), 'What gets turned away')


class PiecePageTests(CafeBase):
    def setUp(self):
        super().setUp()
        self.article = self.make_article(body='First paragraph.\n\n## A heading\n\nSecond.')

    def test_home_shows_the_latest_piece_with_its_coupon_wired_to_the_api(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, self.article.title)
        self.assertContains(response, 'Claim number 1.')
        self.assertContains(response, '<h2>A heading</h2>', html=True)
        self.assertContains(response, '0 of 2 ticked')
        self.assertContains(response, 'Nobody has argued back yet')
        self.assertContains(response, 'Round 1 open')
        self.assertContains(response, reverse('claim-vote', args=[self.article.slug, 1]))
        self.assertContains(response, reverse('piece-replies', args=[self.article.slug]))
        self.assertIn('csrftoken', response.cookies)

    def test_the_page_remembers_your_ticks_and_hides_other_claims_results(self):
        self.make_vote(self.article.claims.last())
        self.client.post(reverse('claim-vote', args=[self.article.slug, 1]), {'choice': VoteChoice.AGREE})
        page = self.client.get(self.article.get_absolute_url())
        self.assertContains(page, '1 of 2 ticked')
        self.assertContains(page, '100% of the cafe agrees', count=1)

    def test_drafts_are_hidden_from_readers_but_the_house_can_preview_them(self):
        draft = self.make_article(slug='draft', published=False, title='Unfinished thoughts')
        self.assertEqual(self.client.get(draft.get_absolute_url()).status_code, 404)
        self.client.force_login(get_user_model().objects.create_superuser('house', password='x'))
        preview = self.client.get(draft.get_absolute_url())
        self.assertContains(preview, 'Unfinished thoughts')
        self.assertContains(preview, 'Draft, only you see this')
        self.assertNotContains(self.client.get(reverse('past_rounds')), 'Unfinished thoughts')

    def test_only_published_replies_are_counted_and_listed(self):
        self.make_reply(self.article, text='A fair argument about space.')
        self.make_reply(self.article, text='Something nasty.', status=ReplyStatus.REJECTED)
        self.make_reply(self.article, text='Waiting for the house.', status=ReplyStatus.REVIEW)
        page = self.client.get(self.article.get_absolute_url())
        self.assertContains(page, '1 reader has replied')
        listing = self.client.get(reverse('replies', args=[self.article.slug]))
        self.assertContains(listing, 'A fair argument about space.')
        self.assertNotContains(listing, 'Something nasty.')
        self.assertNotContains(listing, 'Waiting for the house.')

    def test_arguments_show_backers_credit_and_the_house_reply(self):
        argument = Argument.objects.create(
            article=self.article,
            claim=self.article.claims.first(),
            title='He moved',
            summary='He plays as an 8 now.',
            house_reply='Moving him is the problem.',
        )
        argument.replies.add(
            self.make_reply(self.article, nickname='Marta'), self.make_reply(self.article, nickname='dimi_7')
        )
        page = self.client.get(self.article.get_absolute_url())
        self.assertContains(page, 'He moved')
        self.assertContains(page, '<b>2 readers</b>', html=True)
        self.assertContains(page, 'against claim 1')
        self.assertContains(page, 'First raised by Marta')
        self.assertContains(page, 'Moving him is the problem.')
        self.assertContains(page, 'Round 2 open')

    def test_replies_page_can_be_narrowed_to_one_argument(self):
        argument = Argument.objects.create(article=self.article, title='He moved', summary='He plays as an 8 now.')
        argument.replies.add(self.make_reply(self.article, text='He is an 8 these days.'))
        self.make_reply(self.article, text='A different point entirely.')
        listing = self.client.get(reverse('replies', args=[self.article.slug]), {'argument': argument.id})
        self.assertContains(listing, 'He is an 8 these days.')
        self.assertNotContains(listing, 'A different point entirely.')

    def test_closed_pieces_show_no_reply_form(self):
        self.article.replies_open = False
        self.article.save()
        self.assertNotContains(self.client.get(self.article.get_absolute_url()), 'Post as guest')

    def test_reader_text_is_escaped(self):
        self.make_reply(self.article, nickname='<b>x</b>', text='<script>alert(1)</script> and then some more')
        listing = self.client.get(reverse('replies', args=[self.article.slug]))
        self.assertNotContains(listing, '<script>alert(1)</script>')
        self.assertContains(listing, '&lt;script&gt;alert(1)&lt;/script&gt;')

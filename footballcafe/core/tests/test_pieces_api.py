from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from core.enums import ReplyStatus, VoteChoice
from core.models import Argument

from .base import CafeBase


class PieceListTests(CafeBase):
    def test_lists_published_pieces_newest_first_with_reply_counts(self):
        old = self.make_article(slug='old', published_at=timezone.now() - timedelta(days=3))
        new = self.make_article(slug='new')
        self.make_article(slug='draft', published=False)
        self.make_reply(old)
        self.make_reply(old, status=ReplyStatus.REVIEW)

        body = self.client.get(reverse('piece-list')).json()
        self.assertEqual(body['count'], 2)
        self.assertEqual([piece['slug'] for piece in body['results']], [new.slug, old.slug])
        self.assertEqual(body['results'][1]['reply_count'], 1)
        self.assertEqual(
            set(body['results'][0]),
            {'slug', 'title', 'standfirst', 'reading_minutes', 'published_at', 'replies_open', 'reply_count'},
        )

    def test_page_size_can_be_changed(self):
        for number in range(3):
            self.make_article(slug=f'piece-{number}')
        body = self.client.get(reverse('piece-list'), {'page_size': 2}).json()
        self.assertEqual((body['count'], len(body['results'])), (3, 2))
        self.assertIsNotNone(body['next'])


class PieceDetailTests(CafeBase):
    def setUp(self):
        super().setUp()
        self.article = self.make_article(body='First paragraph.\n\n## A heading\n\nSecond.')
        self.url = reverse('piece-detail', args=[self.article.slug])

    def test_a_new_reader_sees_the_piece_with_an_unticked_coupon(self):
        self.make_vote(self.article.claims.first())
        body = self.client.get(self.url).json()
        self.assertEqual(body['title'], self.article.title)
        self.assertIn('<h2>A heading</h2>', body['body_html'])
        self.assertEqual(body['body'], self.article.body)
        self.assertEqual(body['round_number'], 1)
        self.assertEqual(body['coupon'], {'ticked': 0, 'total': 2, 'verdict': ''})
        self.assertEqual(
            body['claims'][0],
            {'position': 1, 'text': 'Claim number 1.', 'my_choice': None, 'percent_agree': None, 'vote_count': 0},
        )

    def test_arguments_come_most_supported_first_with_credit_and_the_house_reply(self):
        small = Argument.objects.create(article=self.article, title='Small', summary='One reader.')
        small.replies.add(self.make_reply(self.article, nickname='dimi_7'))
        big = Argument.objects.create(
            article=self.article,
            claim=self.article.claims.first(),
            title='Big',
            summary='Two readers.',
            house_reply='Fair point.',
        )
        big.replies.add(self.make_reply(self.article, nickname='Marta'), self.make_reply(self.article))

        body = self.client.get(self.url).json()
        self.assertEqual([argument['title'] for argument in body['arguments']], ['Big', 'Small'])
        self.assertEqual(
            body['arguments'][0],
            {
                'id': big.id,
                'claim_position': 1,
                'title': 'Big',
                'summary': 'Two readers.',
                'supporter_count': 2,
                'first_raised_by': 'Marta',
                'house_reply': 'Fair point.',
            },
        )
        self.assertIsNone(body['arguments'][1]['claim_position'])
        self.assertEqual(body['round_number'], 2)
        self.assertEqual(body['reply_count'], 3)

    def test_drafts_and_unknown_slugs_are_not_found(self):
        draft = self.make_article(slug='draft', published=False)
        self.assertEqual(self.client.get(reverse('piece-detail', args=[draft.slug])).status_code, 404)
        self.assertEqual(self.client.get(reverse('piece-detail', args=['nope'])).status_code, 404)

    def test_the_coupon_is_personal(self):
        self.client.post(reverse('claim-vote', args=[self.article.slug, 1]), {'choice': VoteChoice.DISAGREE})
        mine = self.client.get(self.url).json()['claims'][0]
        self.assertEqual((mine['my_choice'], mine['percent_agree'], mine['vote_count']), (VoteChoice.DISAGREE, 0, 1))
        self.client.cookies.clear()
        self.assertIsNone(self.client.get(self.url).json()['claims'][0]['my_choice'])


class DocsTests(CafeBase):
    def test_schema_and_swagger_are_served(self):
        schema = self.client.get(reverse('schema'))
        self.assertEqual(schema.status_code, 200)
        self.assertIn('/api/pieces/{slug}/claims/{position}/vote/', schema.content.decode())
        self.assertEqual(self.client.get(reverse('swagger-ui')).status_code, 200)

    def test_health_check_answers(self):
        self.assertEqual(self.client.get('/ht/').status_code, 200)

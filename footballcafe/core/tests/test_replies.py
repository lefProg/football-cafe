from unittest import mock

from django.conf import settings
from django.test import override_settings
from django.urls import reverse

from core.agents import moderator
from core.enums import ReplyStatus
from core.models import Argument, Reply

from .base import GOOD_REPLY, CafeBase


def moderator_says(decision, reason=''):
    return mock.patch('core.services.moderator.review', return_value=moderator.Verdict(decision, reason))


class ReplyCreateTests(CafeBase):
    def setUp(self):
        super().setUp()
        self.article = self.make_article()
        self.url = reverse('piece-replies', args=[self.article.slug])

    def post(self, text=GOOD_REPLY, nickname='kopite_nikos', website=None, **headers):
        data = {'nickname': nickname, 'text': text}
        if website is not None:
            data['website'] = website
        return self.client.post(self.url, data, **headers)

    def listed(self):
        return [reply['text'] for reply in self.client.get(self.url).json()['results']]

    def test_a_reply_the_moderator_passes_goes_straight_up(self):
        with moderator_says('publish'):
            response = self.post()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {'status': ReplyStatus.PUBLISHED, 'message': 'Your reply is up.'})
        self.assertIn(settings.CAFE_VISITOR_COOKIE, response.cookies)
        self.assertEqual(self.listed(), [GOOD_REPLY])

    def test_a_rejected_reply_is_kept_out_and_the_reader_is_told_why(self):
        with moderator_says('reject', 'Leave the insult out.'):
            response = self.post()
        self.assertEqual(
            response.json(),
            {
                'status': ReplyStatus.REJECTED,
                'message': 'Not published. Leave the insult out. You can rewrite it and post again.',
            },
        )
        self.assertEqual(Reply.objects.get().moderation_note, 'Leave the insult out.')
        self.assertEqual(self.listed(), [])

    def test_an_unsure_moderator_hands_the_reply_to_the_house(self):
        with moderator_says('unsure', 'Names a crime.'):
            response = self.post()
        self.assertEqual(response.json()['status'], ReplyStatus.REVIEW)
        self.assertIn('The house will read your reply', response.json()['message'])
        self.assertEqual(self.listed(), [])

    def test_without_a_working_moderator_nothing_is_published_automatically(self):
        with mock.patch('core.services.moderator.review', side_effect=moderator.ModeratorUnavailable('no key')):
            response = self.post()
        self.assertEqual(response.json()['status'], ReplyStatus.REVIEW)
        reply = Reply.objects.get()
        self.assertEqual(reply.status, ReplyStatus.REVIEW)
        self.assertIn('no key', reply.moderation_note)

    def test_replies_that_fail_validation_never_reach_the_moderator(self):
        with moderator_says('publish') as review:
            self.assertEqual(
                self.post(nickname='x').json(), {'nickname': ['Pick a nickname between 2 and 30 characters.']}
            )
            self.assertEqual(self.post(nickname='n' * 31).status_code, 400)
            self.assertEqual(
                self.post(text='Too short.').json(),
                {'text': ['That is a bit short for an argument. Give the house a sentence or two.']},
            )
            self.assertEqual(
                self.post(text='a' * 1201).json(), {'text': ['Keep it under 1200 characters. Yours is 1201.']}
            )
            self.assertEqual(self.client.post(self.url, {}).status_code, 400)
        review.assert_not_called()
        self.assertEqual(Reply.objects.count(), 0)

    def test_nickname_spacing_is_tidied(self):
        with moderator_says('publish'):
            self.post(nickname='  big   dave ')
        self.assertEqual(Reply.objects.get().nickname, 'big dave')

    def test_one_visitor_cannot_flood_the_cafe(self):
        with moderator_says('publish'):
            for _ in range(settings.CAFE_REPLY_LIMIT):
                self.assertEqual(self.post().status_code, 201)
            response = self.post()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(
            response.json(), {'detail': 'You have posted a few replies in a row. Give it ten minutes, then come back.'}
        )
        self.assertEqual(Reply.objects.count(), settings.CAFE_REPLY_LIMIT)

    @override_settings(CAFE_REPLY_LIMIT_PER_IP=2)
    def test_one_address_cannot_flood_the_cafe_by_dropping_its_cookie(self):
        with moderator_says('publish'):
            for _ in range(2):
                self.client.cookies.clear()
                self.assertEqual(self.post().status_code, 201)
            self.client.cookies.clear()
            self.assertEqual(self.post().status_code, 429)

    def test_behind_the_https_proxy_the_limit_follows_the_real_visitor_not_the_proxy(self):
        def post_from(address):
            self.client.cookies.clear()
            return self.post(HTTP_X_FORWARDED_FOR=f'10.9.9.9, {address}')

        with override_settings(CAFE_REPLY_LIMIT_PER_IP=1, HTTPS=True), moderator_says('publish'):
            self.assertEqual(post_from('203.0.113.5').status_code, 201)
            self.assertEqual(post_from('203.0.113.5').status_code, 429)
            self.assertEqual(post_from('203.0.113.77').status_code, 201)

    def test_on_a_bare_port_a_typed_in_forwarded_header_is_ignored(self):
        with override_settings(CAFE_REPLY_LIMIT_PER_IP=1), moderator_says('publish'):
            self.assertEqual(self.post(HTTP_X_FORWARDED_FOR='1.1.1.1').status_code, 201)
            self.client.cookies.clear()
            self.assertEqual(self.post(HTTP_X_FORWARDED_FOR='2.2.2.2').status_code, 429)

    def test_bots_that_fill_the_hidden_field_are_quietly_dropped(self):
        with moderator_says('publish') as review:
            response = self.post(website='http://spam.example')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['status'], ReplyStatus.REVIEW)
        review.assert_not_called()
        self.assertEqual(Reply.objects.count(), 0)

    def test_closed_pieces_take_no_replies(self):
        self.article.replies_open = False
        self.article.save()
        with moderator_says('publish'):
            response = self.post()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {'detail': 'Replies to this piece are closed.'})

    def test_drafts_take_no_replies(self):
        draft = self.make_article(slug='draft', published=False)
        with moderator_says('publish'):
            response = self.client.post(
                reverse('piece-replies', args=[draft.slug]), {'nickname': 'kopite_nikos', 'text': GOOD_REPLY}
            )
        self.assertEqual(response.status_code, 404)


class ReplyListTests(CafeBase):
    def setUp(self):
        super().setUp()
        self.article = self.make_article()
        self.url = reverse('piece-replies', args=[self.article.slug])

    def test_only_published_replies_oldest_first_without_private_fields(self):
        first = self.make_reply(self.article, text='First point about the piece.')
        self.make_reply(self.article, text='Something nasty.', status=ReplyStatus.REJECTED)
        self.make_reply(self.article, text='Waiting.', status=ReplyStatus.REVIEW)
        self.make_reply(self.article, text='Second point about the piece.')
        body = self.client.get(self.url).json()
        self.assertEqual(
            [reply['text'] for reply in body['results']],
            ['First point about the piece.', 'Second point about the piece.'],
        )
        self.assertEqual(set(body['results'][0]), {'uuid', 'nickname', 'text', 'created_at'})
        self.assertEqual(body['results'][0]['uuid'], str(first.uuid))

    def test_argument_filter_narrows_to_the_replies_behind_it(self):
        argument = Argument.objects.create(article=self.article, title='He moved', summary='He is an 8 now.')
        argument.replies.add(self.make_reply(self.article, text='He is an 8 these days.'))
        self.make_reply(self.article, text='A different point entirely.')
        body = self.client.get(self.url, {'argument': argument.id}).json()
        self.assertEqual([reply['text'] for reply in body['results']], ['He is an 8 these days.'])

    def test_an_argument_of_another_piece_gives_nothing(self):
        other = self.make_article(slug='other')
        argument = Argument.objects.create(article=other, title='Elsewhere', summary='Not this piece.')
        argument.replies.add(self.make_reply(other))
        self.make_reply(self.article)
        self.assertEqual(self.client.get(self.url, {'argument': argument.id}).json()['count'], 0)

    def test_a_bad_argument_value_is_a_400(self):
        response = self.client.get(self.url, {'argument': 'abc'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'argument': ['A valid integer is required.']})

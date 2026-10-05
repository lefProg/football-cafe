from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError

from core.agents import notetaker
from core.enums import ReplyStatus
from core.models import Argument

from .base import CafeBase
from .fakes import FakeClaude, use


def group(reply_ids, title='He moved', summary='He plays as an 8 now.', claim_number=1, existing_id=0):
    return {
        'existing_id': existing_id,
        'title': title,
        'summary': summary,
        'claim_number': claim_number,
        'reply_ids': reply_ids,
    }


class NoteTakerTests(CafeBase):
    def setUp(self):
        super().setUp()
        self.article = self.make_article()
        self.space = self.make_reply(self.article, text='There is no space between the lines any more.')
        self.moved = self.make_reply(self.article, nickname='Marta', text='He is an 8 these days.')
        self.hidden = self.make_reply(self.article, text='Something nasty.', status=ReplyStatus.REJECTED)

    def take_notes(self, *groups):
        fake = FakeClaude({'arguments': list(groups)})
        with use(fake):
            count = notetaker.take_notes(self.article)
        return count, fake

    def test_groups_become_arguments_linked_to_the_real_replies(self):
        count, _ = self.take_notes(
            group([self.space.id], title='The space is gone', summary='No room between the lines.'),
            group([self.moved.id], claim_number=0),
        )
        self.assertEqual(count, 2)
        space = Argument.objects.get(title='The space is gone')
        self.assertEqual(list(space.replies.all()), [self.space])
        self.assertEqual(space.claim.position, 1)
        self.assertIsNone(Argument.objects.get(title='He moved').claim)

    def test_only_published_replies_are_sent_and_the_house_text_is_context(self):
        _, fake = self.take_notes(group([self.space.id]))
        payload = fake.payload()
        self.assertEqual([reply['id'] for reply in payload['replies']], [self.space.id, self.moved.id])
        self.assertNotIn('nickname', payload['replies'][0])
        self.assertEqual(payload['piece']['claims'][0], {'number': 1, 'text': 'Claim number 1.'})
        self.assertEqual(fake.requests[0]['output_config']['format']['schema'], notetaker.SCHEMA)

    def test_made_up_or_hidden_reply_ids_are_thrown_out(self):
        count, _ = self.take_notes(
            group([self.space.id, 99999, self.hidden.id]),
            group([424242], title='Invented', summary='Nobody said this.'),
        )
        self.assertEqual(count, 1)
        self.assertEqual(list(Argument.objects.get().replies.all()), [self.space])

    def test_a_reply_backs_one_argument_only(self):
        self.take_notes(group([self.space.id]), group([self.space.id, self.moved.id], title='Second'))
        self.assertEqual(list(Argument.objects.get(title='Second').replies.all()), [self.moved])

    def test_no_more_than_four_arguments(self):
        extra = [self.make_reply(self.article, text=f'Point number {n} about the piece.') for n in range(4)]
        count, _ = self.take_notes(
            *[group([reply.id], title=f'Point {n}') for n, reply in enumerate(extra)],
            group([self.space.id], title='One too many'),
        )
        self.assertEqual(count, 4)
        self.assertFalse(Argument.objects.filter(title='One too many').exists())

    def test_a_second_run_keeps_answered_arguments_and_clears_stale_ones(self):
        answered = Argument.objects.create(
            article=self.article, title='He moved', summary='Old summary.', house_reply='Moving him is the problem.'
        )
        stale = Argument.objects.create(article=self.article, title='Stale', summary='Nobody says this now.')
        dropped_but_answered = Argument.objects.create(
            article=self.article,
            title='Answered long ago',
            summary='Still on the page.',
            house_reply='Already settled.',
        )
        self.take_notes(group([self.moved.id], title='A new title', summary='New summary.', existing_id=answered.id))

        answered.refresh_from_db()
        self.assertEqual(answered.title, 'He moved')
        self.assertEqual(answered.summary, 'New summary.')
        self.assertEqual(answered.house_reply, 'Moving him is the problem.')
        self.assertEqual(list(answered.replies.all()), [self.moved])
        self.assertFalse(Argument.objects.filter(id=stale.id).exists())
        self.assertTrue(Argument.objects.filter(id=dropped_but_answered.id).exists())

    def test_an_unknown_existing_id_makes_a_new_argument(self):
        self.take_notes(group([self.space.id], existing_id=31337))
        self.assertEqual(Argument.objects.count(), 1)

    def test_nothing_to_sum_up_and_claude_trouble_are_reported_plainly(self):
        empty = self.make_article(slug='quiet-piece')
        with self.assertRaisesMessage(notetaker.NoteTakerError, 'no published replies'):
            notetaker.take_notes(empty)
        with use(FakeClaude(raises=TypeError('no credentials'))):
            with self.assertRaisesMessage(notetaker.NoteTakerError, 'ANTHROPIC_API_KEY'):
                notetaker.take_notes(self.article)
        self.assertEqual(Argument.objects.count(), 0)

    def test_the_command_runs_the_note_taker(self):
        out = StringIO()
        with use(FakeClaude({'arguments': [group([self.space.id])]})):
            call_command('take_notes', self.article.slug, stdout=out)
        self.assertIn('1 argument on the page now', out.getvalue())
        with self.assertRaises(CommandError):
            call_command('take_notes', 'no-such-piece')

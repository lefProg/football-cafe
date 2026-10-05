from datetime import timedelta

from django.utils import timezone

from core.enums import ReplyStatus, VoteChoice
from core.models import Argument, Article, Reply

from .base import CafeBase


class ClaimTallyTests(CafeBase):
    def test_no_votes_gives_no_percentage(self):
        claim = self.make_article().claims.first()
        self.assertEqual(claim.tally(), (None, 0))

    def test_percentage_is_share_of_agree_votes(self):
        claim = self.make_article().claims.first()
        for choice in (VoteChoice.AGREE, VoteChoice.AGREE, VoteChoice.DISAGREE):
            self.make_vote(claim, choice)
        self.assertEqual(claim.tally(), (67, 3))


class ArticleTests(CafeBase):
    def test_published_excludes_drafts_and_future_pieces(self):
        live = self.make_article()
        self.make_article(slug='draft', published=False)
        self.make_article(slug='future', published_at=timezone.now() + timedelta(days=1))
        self.assertEqual(list(Article.objects.published()), [live])

    def test_reply_count_annotation_counts_published_replies_only(self):
        article = self.make_article()
        self.make_reply(article)
        self.make_reply(article, status=ReplyStatus.REJECTED)
        self.assertEqual(Article.objects.published().with_reply_count().get().reply_count, 1)

    def test_round_two_starts_with_the_first_house_reply(self):
        article = self.make_article()
        argument = Argument.objects.create(article=article, title='He moved', summary='He plays as an 8 now.')
        self.assertEqual(article.round_number, 1)
        argument.house_reply = 'Moving him is the problem.'
        argument.save()
        self.assertEqual(article.round_number, 2)


class ReplyManagerTests(CafeBase):
    def test_queue_and_published_are_separate(self):
        article = self.make_article()
        up = self.make_reply(article)
        waiting = self.make_reply(article, status=ReplyStatus.REVIEW)
        self.make_reply(article, status=ReplyStatus.REJECTED)
        self.assertEqual(list(Reply.objects.published()), [up])
        self.assertEqual(list(Reply.objects.waiting_for_the_house()), [waiting])

    def test_recent_by_looks_at_one_visitor_inside_the_window(self):
        article = self.make_article()
        mine = self.make_reply(article)
        self.make_reply(article)
        old = self.make_reply(article, visitor=mine.visitor)
        Reply.objects.filter(id=old.id).update(created_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(list(Reply.objects.recent_by(mine.visitor, 600)), [mine])


class ArgumentTests(CafeBase):
    def setUp(self):
        super().setUp()
        self.article = self.make_article()
        self.argument = Argument.objects.create(article=self.article, title='He moved', summary='He plays as an 8 now.')

    def test_one_reader_counts_once_and_hidden_replies_do_not_count(self):
        nikos = self.make_reply(self.article)
        self.argument.replies.add(
            nikos,
            self.make_reply(self.article, visitor=nikos.visitor, text='And another thing.'),
            self.make_reply(self.article, nickname='Marta'),
            self.make_reply(self.article, nickname='troll', status=ReplyStatus.REJECTED),
        )
        self.assertEqual(self.argument.supporter_count(), 2)

    def test_credit_goes_to_the_earliest_published_reply(self):
        first = self.make_reply(self.article, nickname='early_bird', status=ReplyStatus.REJECTED)
        second = self.make_reply(self.article, nickname='Marta')
        third = self.make_reply(self.article, nickname='dimi_7')
        self.argument.replies.add(first, second, third)
        self.assertEqual(self.argument.first_raised_by(), 'Marta')

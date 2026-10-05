"""Shared factories for the tests. No test talks to Claude: see fakes.py."""

import uuid

from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from core.enums import ReplyStatus, VoteChoice
from core.models import Article, Reply, Vote

GOOD_REPLY = 'The space between the lines is gone, and trust has nothing to do with it.'


class CafeBase(APITestCase):
    def setUp(self):
        cache.clear()

    # ---- factories ----
    @staticmethod
    def make_article(claims=2, published=True, **kwargs):
        defaults = {
            'title': 'The No. 10 never died',
            'slug': 'no-10-never-died',
            'standfirst': 'Everyone blames the press.',
            'body': "Ask anyone why the playmaker vanished.\n\nI don't buy it.",
            'published_at': timezone.now() if published else None,
        }
        defaults.update(kwargs)
        article = Article.objects.create(**defaults)
        for position in range(1, claims + 1):
            article.claims.create(position=position, text=f'Claim number {position}.')
        return article

    @staticmethod
    def make_reply(article, text='The space is gone, not the trust.', status=ReplyStatus.PUBLISHED, **kwargs):
        defaults = {'visitor': uuid.uuid4(), 'nickname': 'kopite_nikos'}
        defaults.update(kwargs)
        return Reply.objects.create(article=article, text=text, status=status, **defaults)

    @staticmethod
    def make_vote(claim, choice=VoteChoice.AGREE, visitor=None):
        return Vote.objects.create(claim=claim, visitor=visitor or uuid.uuid4(), choice=choice)

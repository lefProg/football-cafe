from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from core.models import Article


class PieceSitemap(Sitemap):
    """Every published piece. Drafts and pieces dated in the future are left out."""

    def items(self):
        return Article.objects.published()

    def lastmod(self, article):
        return max(article.updated_at, article.published_at)


class PageSitemap(Sitemap):
    """The few pages that are not pieces."""

    def items(self):
        return ['home', 'past_rounds', 'house_rules']

    def location(self, name):
        return reverse(name)


SITEMAPS = {'pieces': PieceSitemap, 'pages': PageSitemap}

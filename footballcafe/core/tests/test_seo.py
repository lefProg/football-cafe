import json
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from .base import CafeBase


def structured_data(response):
    found = re.search(r'<script type="application/ld\+json">(.*?)</script>', response.content.decode(), re.S)
    return json.loads(found.group(1)) if found else None


class SearchEngineTests(CafeBase):
    def setUp(self):
        super().setUp()
        self.article = self.make_article(standfirst='Everyone blames the press. "Wrong," says the house.')
        self.address = 'http://testserver' + self.article.get_absolute_url()

    def test_robots_keeps_the_admin_and_api_out_and_points_at_the_sitemap(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response['Content-Type'], 'text/plain')
        text = response.content.decode()
        self.assertIn('Disallow: /counter/', text)
        self.assertIn('Disallow: /api/', text)
        self.assertIn('Sitemap: http://testserver/sitemap.xml', text)

    def test_sitemap_lists_published_pieces_and_the_fixed_pages_only(self):
        self.make_article(slug='draft', published=False)
        self.make_article(slug='future', published_at=timezone.now() + timedelta(days=1))
        text = self.client.get('/sitemap.xml').content.decode()
        self.assertIn(f'<loc>{self.address}</loc>', text)
        self.assertIn('<lastmod>', text)
        self.assertIn('<loc>http://testserver/house-rules/</loc>', text)
        self.assertNotIn('draft', text)
        self.assertNotIn('future', text)

    def test_a_piece_has_one_address_even_when_it_is_shown_on_the_home_page(self):
        for url in (reverse('home'), self.article.get_absolute_url()):
            self.assertContains(self.client.get(url), f'<link rel="canonical" href="{self.address}">')

    def test_a_piece_carries_what_a_link_preview_needs(self):
        page = self.client.get(self.article.get_absolute_url())
        self.assertContains(page, '<meta property="og:type" content="article">')
        self.assertContains(page, f'<meta property="og:title" content="{self.article.title}">')
        self.assertContains(page, f'<meta property="og:url" content="{self.address}">')
        self.assertContains(page, '<meta property="og:image" content="http://testserver/static/og-default.png">')
        self.assertContains(page, '<meta name="twitter:card" content="summary_large_image">')
        self.assertContains(page, 'Everyone blames the press. &quot;Wrong,&quot; says the house.')

    def test_a_piece_is_labelled_as_an_article_for_google(self):
        self.make_reply(self.article)
        data = structured_data(self.client.get(self.article.get_absolute_url()))
        self.assertEqual(data['@type'], 'OpinionNewsArticle')
        self.assertEqual(data['headline'], self.article.title)
        self.assertEqual(data['description'], self.article.standfirst)
        self.assertEqual(data['mainEntityOfPage'], self.address)
        self.assertEqual(data['commentCount'], 1)
        self.assertEqual(data['publisher']['name'], 'Football Cafe')
        self.assertTrue(data['datePublished'].startswith(str(self.article.published_at.year)))

    def test_text_in_the_labels_cannot_break_out_of_the_script_tag(self):
        nasty = self.make_article(slug='nasty', title='Ten </script><script>alert(1)</script> things')
        page = self.client.get(nasty.get_absolute_url())
        self.assertNotContains(page, '</script><script>alert(1)')
        self.assertEqual(structured_data(page)['headline'], nasty.title)

    def test_a_draft_preview_is_kept_out_of_search(self):
        draft = self.make_article(slug='draft', published=False)
        self.client.force_login(get_user_model().objects.create_superuser('house', password='x'))
        page = self.client.get(draft.get_absolute_url())
        self.assertContains(page, '<meta name="robots" content="noindex">')
        self.assertIsNone(structured_data(page))

    def test_narrowed_reply_lists_point_at_the_full_list(self):
        page = self.client.get(reverse('replies', args=[self.article.slug]), {'argument': 5})
        self.assertContains(page, f'<link rel="canonical" href="{self.address}replies/">')

    @override_settings(SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'), ALLOWED_HOSTS=['football-cafe.xyz'])
    def test_behind_the_https_proxy_every_address_is_the_public_https_one(self):
        proxied = {'HTTP_HOST': 'football-cafe.xyz', 'HTTP_X_FORWARDED_PROTO': 'https'}
        public = 'https://football-cafe.xyz' + self.article.get_absolute_url()
        page = self.client.get(self.article.get_absolute_url(), **proxied)
        self.assertContains(page, f'<link rel="canonical" href="{public}">')
        self.assertContains(
            page, '<meta property="og:image" content="https://football-cafe.xyz/static/og-default.png">'
        )
        self.assertEqual(structured_data(page)['mainEntityOfPage'], public)
        self.assertIn(f'<loc>{public}</loc>', self.client.get('/sitemap.xml', **proxied).content.decode())
        self.assertIn(
            'Sitemap: https://football-cafe.xyz/sitemap.xml', self.client.get('/robots.txt', **proxied).content.decode()
        )

    def test_other_pages_get_the_site_preview(self):
        page = self.client.get(reverse('house_rules'))
        self.assertContains(page, '<meta property="og:type" content="website">')
        self.assertContains(page, '<meta property="og:title" content="Football Cafe">')

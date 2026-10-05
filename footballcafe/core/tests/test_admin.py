from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from core.enums import ReplyStatus
from core.models import Argument, Article

from .base import CafeBase
from .fakes import FakeClaude, use


class AdminTests(CafeBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(get_user_model().objects.create_superuser('house', password='x'))
        self.article = self.make_article()
        self.reply = self.make_reply(self.article, status=ReplyStatus.REVIEW)

    def action(self, model, name, *ids):
        return self.client.post(
            reverse(f'admin:core_{model}_changelist'), {'action': name, '_selected_action': list(ids)}, follow=True
        )

    def test_every_admin_screen_opens(self):
        for model in ('article', 'reply', 'argument'):
            self.assertEqual(self.client.get(reverse(f'admin:core_{model}_changelist')).status_code, 200)
            self.assertEqual(self.client.get(reverse(f'admin:core_{model}_add')).status_code, 200)

    def test_the_piece_form_has_the_editor_claims_and_arguments_on_one_screen(self):
        Argument.objects.create(article=self.article, title='He moved', summary='He plays as an 8 now.')
        page = self.client.get(reverse('admin:core_article_change', args=[self.article.id]))
        self.assertContains(page, 'data-preview-url="/counter/core/article/preview/"')
        self.assertContains(page, 'js/admin_article.js')
        self.assertContains(page, 'The coupon: the claims this piece stands on')
        self.assertContains(page, 'Claim number 1.')
        self.assertContains(page, 'He moved')
        self.assertContains(page, 'View on site')

    def test_the_piece_list_points_at_replies_waiting_for_the_house(self):
        page = self.client.get(reverse('admin:core_article_changelist'))
        self.assertContains(page, '1 to read')
        self.assertContains(page, f'status__exact={ReplyStatus.REVIEW}')

    def test_preview_renders_markdown_like_the_site_and_is_for_staff_only(self):
        url = reverse('admin:core_article_preview')
        response = self.client.post(url, {'body': '## Heading\n\n> A quote'})
        self.assertContains(response, '<h2>Heading</h2>', html=True)
        self.assertContains(response, '<blockquote>')
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.post(url, {'body': 'x'}).status_code, 302)

    def test_saving_a_piece_works_out_the_reading_time(self):
        data = {
            'title': 'A long read',
            'slug': 'a-long-read',
            'standfirst': 'Short.',
            'body': 'word ' * 1000,
            'published_at_0': '',
            'published_at_1': '',
            'replies_open': 'on',
            'claims-TOTAL_FORMS': 1,
            'claims-INITIAL_FORMS': 0,
            'claims-MIN_NUM_FORMS': 1,
            'claims-MAX_NUM_FORMS': 1000,
            'claims-0-position': 1,
            'claims-0-text': 'One claim.',
            'arguments-TOTAL_FORMS': 0,
            'arguments-INITIAL_FORMS': 0,
            'arguments-MIN_NUM_FORMS': 0,
            'arguments-MAX_NUM_FORMS': 1000,
        }
        response = self.client.post(reverse('admin:core_article_add'), data)
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None) and response.context['errors'])
        piece = Article.objects.get(slug='a-long-read')
        self.assertEqual(piece.reading_minutes, 4)
        self.assertFalse(piece.is_published)
        self.assertEqual(piece.claims.get().text, 'One claim.')

    def test_publish_and_unpublish_actions(self):
        draft = self.make_article(slug='draft', published=False)
        self.action('article', 'publish_now', draft.id)
        draft.refresh_from_db()
        self.assertTrue(draft.is_published)
        self.assertLessEqual(draft.published_at, timezone.now())
        self.action('article', 'back_to_draft', draft.id)
        draft.refresh_from_db()
        self.assertIsNone(draft.published_at)

    def test_the_house_can_publish_a_reply_from_its_queue(self):
        self.action('reply', 'publish', self.reply.id)
        self.reply.refresh_from_db()
        self.assertEqual(self.reply.status, ReplyStatus.PUBLISHED)

    def test_the_house_can_ask_the_note_taker_from_the_piece_list(self):
        self.reply.status = ReplyStatus.PUBLISHED
        self.reply.save()
        answer = {
            'arguments': [
                {
                    'existing_id': 0,
                    'title': 'The space is gone',
                    'summary': 'No room.',
                    'claim_number': 1,
                    'reply_ids': [self.reply.id],
                }
            ]
        }
        with use(FakeClaude(answer)):
            response = self.action('article', 'sum_up_replies', self.article.id)
        self.assertContains(response, '1 argument on the page now.')
        self.assertEqual(Argument.objects.get().title, 'The space is gone')

    def test_note_taker_trouble_is_shown_to_the_house(self):
        self.reply.status = ReplyStatus.PUBLISHED
        self.reply.save()
        with use(FakeClaude(raises=TypeError('no credentials'))):
            response = self.action('article', 'sum_up_replies', self.article.id)
        self.assertContains(response, 'ANTHROPIC_API_KEY')

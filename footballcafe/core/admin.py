from django.contrib import admin, messages
from django.http import HttpResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.views.decorators.http import require_POST

from core.agents import notetaker
from core.enums import ReplyStatus
from core.models import Argument, Article, Claim, Reply
from core.templatetags.core_extras import markdown

WORDS_PER_MINUTE = 230


class ClaimInline(admin.TabularInline):
    model = Claim
    extra = 0
    min_num = 1
    verbose_name = 'claim'
    verbose_name_plural = 'The coupon: the claims this piece stands on'


class ArgumentInline(admin.StackedInline):
    """The arguments the note-taker found, so the house can answer them without leaving the piece."""

    model = Argument
    extra = 0
    fields = ['title', 'summary', 'claim', 'backers', 'house_reply']
    readonly_fields = ['backers']
    verbose_name = 'argument'
    verbose_name_plural = 'The cafe answers back: arguments from readers, and your replies'

    @admin.display(description='Readers behind it')
    def backers(self, argument):
        return argument.supporter_count() if argument.pk else '-'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'claim':
            article_id = request.resolver_match.kwargs.get('object_id')
            kwargs['queryset'] = Claim.objects.filter(article_id=article_id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ['title', 'state', 'published_at', 'replies_open', 'reply_count', 'waiting']
    list_editable = ['replies_open']
    search_fields = ['title', 'standfirst', 'body']
    prepopulated_fields = {'slug': ['title']}
    readonly_fields = ['reading_minutes']
    save_on_top = True
    inlines = [ClaimInline, ArgumentInline]
    actions = ['publish_now', 'back_to_draft', 'sum_up_replies']
    fieldsets = [
        (None, {'fields': ['title', 'slug', 'standfirst']}),
        (
            'The piece',
            {
                'fields': ['body'],
                'description': 'Type on the left. The right side shows the piece as readers will see it.',
            },
        ),
        ('Publishing', {'fields': ['published_at', 'replies_open', 'reading_minutes']}),
    ]

    class Media:
        css = {'all': ['css/fonts.css', 'css/admin_article.css']}
        js = ['js/admin_article.js']

    # ---- list columns ----
    @admin.display(description='State')
    def state(self, article):
        if article.is_published:
            return 'Live'
        return 'Scheduled' if article.published_at else 'Draft'

    @admin.display(description='Published replies')
    def reply_count(self, article):
        return article.replies.published().count()

    @admin.display(description='Waiting for you')
    def waiting(self, article):
        count = article.replies.waiting_for_the_house().count()
        if not count:
            return '-'
        url = (
            reverse('admin:core_reply_changelist')
            + f'?status__exact={ReplyStatus.REVIEW}&article__id__exact={article.id}'
        )
        return format_html('<a href="{}">{} to read</a>', url, count)

    # ---- the form ----
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == 'body':
            field.widget.attrs.update({'rows': 32, 'data-preview-url': reverse('admin:core_article_preview')})
        elif db_field.name == 'standfirst':
            field.widget.attrs.update({'rows': 3})
        return field

    def save_model(self, request, article, form, change):
        article.reading_minutes = max(1, round(len(article.body.split()) / WORDS_PER_MINUTE))
        super().save_model(request, article, form, change)

    def get_urls(self):
        preview = path('preview/', self.admin_site.admin_view(require_POST(self.preview)), name='core_article_preview')
        return [preview] + super().get_urls()

    def preview(self, request):
        """The Markdown in the form, rendered the way the site renders it."""
        return HttpResponse(markdown(request.POST.get('body', '')))

    # ---- actions ----
    @admin.action(description='Publish now')
    def publish_now(self, request, queryset):
        count = queryset.update(published_at=timezone.now())
        self.message_user(request, f'{count} piece{"" if count == 1 else "s"} live.')

    @admin.action(description='Take offline (back to draft)')
    def back_to_draft(self, request, queryset):
        count = queryset.update(published_at=None)
        self.message_user(request, f'{count} piece{"" if count == 1 else "s"} back to draft.')

    @admin.action(description='Ask the note-taker to sum up the replies')
    def sum_up_replies(self, request, queryset):
        for article in queryset:
            try:
                count = notetaker.take_notes(article)
            except notetaker.NoteTakerError as error:
                self.message_user(request, f'{article}: {error}', level=messages.ERROR)
            else:
                self.message_user(request, f'{article}: {count} argument{"" if count == 1 else "s"} on the page now.')


@admin.register(Reply)
class ReplyAdmin(admin.ModelAdmin):
    list_display = ['nickname', 'short_text', 'article', 'status', 'moderation_note', 'created_at']
    list_filter = ['status', 'article']
    search_fields = ['nickname', 'text']
    readonly_fields = ['uuid', 'visitor', 'created_at']
    actions = ['publish', 'reject']

    @admin.display(description='Reply')
    def short_text(self, reply):
        return reply.text[:90]

    @admin.action(description='Publish the selected replies')
    def publish(self, request, queryset):
        queryset.update(status=ReplyStatus.PUBLISHED)

    @admin.action(description='Reject the selected replies')
    def reject(self, request, queryset):
        queryset.update(status=ReplyStatus.REJECTED)


@admin.register(Argument)
class ArgumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'article', 'claim', 'supporter_count', 'answered']
    list_filter = ['article']
    filter_horizontal = ['replies']

    @admin.display(boolean=True, description='House replied')
    def answered(self, argument):
        return bool(argument.house_reply)

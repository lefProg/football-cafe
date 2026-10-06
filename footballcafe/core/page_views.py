"""The pages people read. They only show things: every vote and reply goes through the API (views.py)."""

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie

from core import services
from core.models import Article


def _article_data(request, article) -> dict:
    """The piece described the way Google reads articles (schema.org), for the page's structured data."""
    cafe = {'@type': 'Organization', 'name': 'Football Cafe', 'url': request.build_absolute_uri(reverse('home'))}
    return {
        '@context': 'https://schema.org',
        '@type': 'OpinionNewsArticle',
        'headline': article.title,
        'description': article.standfirst,
        'datePublished': article.published_at.isoformat(),
        'dateModified': max(article.updated_at, article.published_at).isoformat(),
        'mainEntityOfPage': request.build_absolute_uri(article.get_absolute_url()),
        'image': request.build_absolute_uri(static('og-default.png')),
        'author': cafe,
        'publisher': cafe,
        'commentCount': article.replies.published().count(),
    }


def _piece_context(request, article, nav='') -> dict:
    arguments = sorted(
        article.arguments.select_related('claim'),
        key=lambda argument: argument.supporter_count(),
        reverse=True,
    )
    return {
        'nav': nav,
        # One address per piece for search engines, also when it is shown as today's piece on the home page.
        'canonical': request.build_absolute_uri(article.get_absolute_url()),
        'article_data': _article_data(request, article) if article.is_published else None,
        'article': article,
        'coupon': services.coupon_state(article, services.get_visitor(request)),
        'arguments': arguments,
        'answered': [argument for argument in arguments if argument.house_reply],
        'reply_count': article.replies.published().count(),
        'text_max': services.TEXT_MAX,
        'nickname_max': services.NICKNAME_MAX,
    }


@ensure_csrf_cookie
def home(request):
    article = Article.objects.published().first()
    if article is None:
        return render(request, 'empty.html', {'nav': 'home'})
    return render(request, 'article.html', _piece_context(request, article, nav='home'))


@ensure_csrf_cookie
def article(request, slug):
    article = get_object_or_404(Article, slug=slug)
    # A draft is a page only the house can open, to see the piece as readers will.
    if not article.is_published and not request.user.is_staff:
        raise Http404
    return render(request, 'article.html', _piece_context(request, article))


def past_rounds(request):
    pieces = Article.objects.published().with_reply_count()
    return render(request, 'past_rounds.html', {'pieces': pieces, 'nav': 'past'})


def replies(request, slug):
    article = get_object_or_404(Article.objects.published(), slug=slug)
    published = article.replies.published()
    argument = None
    if request.GET.get('argument', '').isdigit():
        argument = article.arguments.filter(id=request.GET['argument']).first()
    if argument:
        published = published.filter(arguments=argument)
    return render(
        request,
        'replies.html',
        {
            'article': article,
            'replies': published,
            'argument': argument,
            'reply_count': published.count(),
            # The narrowed lists (?argument=) are the same replies again, so they point at the full list.
            'canonical': request.build_absolute_uri(reverse('replies', args=[article.slug])),
        },
    )


def house_rules(request):
    return render(request, 'house_rules.html', {'nav': 'rules'})


def robots(request):
    """Tells search engines what to read: the pages, not the admin or the raw API."""
    lines = [
        'User-agent: *',
        'Disallow: /counter/',
        'Disallow: /api/',
        '',
        f'Sitemap: {request.build_absolute_uri(reverse("sitemap"))}',
    ]
    return HttpResponse('\n'.join(lines) + '\n', content_type='text/plain')

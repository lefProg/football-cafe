from django.urls import path

from core import page_views

urlpatterns = [
    path('', page_views.home, name='home'),
    path('pieces/', page_views.past_rounds, name='past_rounds'),
    path('pieces/<slug:slug>/', page_views.article, name='article'),
    path('pieces/<slug:slug>/replies/', page_views.replies, name='replies'),
    path('house-rules/', page_views.house_rules, name='house_rules'),
]

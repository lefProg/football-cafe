from django.contrib import admin
from django.urls import include, path

admin.site.site_header = 'Football Cafe, behind the counter'
admin.site.site_title = 'Football Cafe'
admin.site.index_title = 'Pieces, replies and arguments'

urlpatterns = [
    path('counter/', admin.site.urls),
    path('api/', include('core.urls')),
    path('ht/', include('health_check.urls')),
    path('', include('core.page_urls')),
]

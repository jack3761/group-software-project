from django.contrib import admin
from django.urls import path, include

# (Michael Hills)
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('base.urls')),
]

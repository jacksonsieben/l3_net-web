"""
URL configuration for l3net_web project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from main import views as main_views
from django.http import JsonResponse

def health_check(request):
    """Health check endpoint for load balancers and monitoring"""
    return JsonResponse({'status': 'healthy', 'service': 'l3net_web'})

urlpatterns = [
    path('health/', health_check, name='health_check'),
    path('admin/', admin.site.urls),
    path('users/', include('users.urls')),
    path('validation/', include('validation.urls')),
    path('api/', include('validation.api_urls')),
    path('api-auth/', include('rest_framework.urls')),  # For browsable API authentication
    path('', main_views.home, name='home'),
]

# Add media serving in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # In development, let Django handle static files automatically
    # Don't explicitly add static URL patterns as Django's staticfiles app handles this

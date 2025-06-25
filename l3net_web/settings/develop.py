import os
from .base import *

# Override settings for production
DEBUG = True
STATIC_ROOT = '/app/staticfiles'
MEDIA_ROOT = '/app/media'
# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-*3o)i**vxk@$8lt9!%ts1j(4=bvesubqk^l8h=9v0%$+t1d*h3')

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '0.0.0.0,localhost,127.0.0.1').split(',')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'l3net_db',
        'USER': 'l3net_admin',
        'PASSWORD': 'l3net_pass123',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
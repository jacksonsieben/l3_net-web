from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import api_views

app_name = 'validation_api'

urlpatterns = [
    # Authentication endpoints
    path('auth/token/', api_views.CustomAuthToken.as_view(), name='api_token'),
    path('auth/logout/', api_views.logout_user, name='api_logout'),
    path('auth/profile/', api_views.user_profile, name='api_profile'),
    
    # Status endpoint
    path('status/', api_views.api_status, name='api_status'),
    
    # Exam endpoints
    path('exams/', api_views.ExamListCreateView.as_view(), name='exam_list_create'),
    path('exams/<int:pk>/', api_views.ExamDetailView.as_view(), name='exam_detail'),
    path('exams/external/<str:external_id>/', api_views.get_exam_by_external_id, name='get_exam_by_external_id'),
    
    # Model version endpoints
    path('model-versions/', api_views.ModelVersionListCreateView.as_view(), name='model_version_list_create'),
    
    # Run endpoints
    path('runs/', api_views.RunListCreateView.as_view(), name='run_list_create'),
    path('runs/<int:pk>/', api_views.RunDetailView.as_view(), name='run_detail'),
    path('runs/with-predictions/', api_views.create_run_with_predictions, name='create_run_with_predictions'),
    path('runs/<int:run_id>/predictions/', api_views.add_predictions_to_run, name='add_predictions_to_run'),
    path('runs/<int:run_id>/predictions/get/', api_views.get_run_predictions, name='get_run_predictions'),
    
    # Assignment endpoints
    path('assign-run/', api_views.assign_run_to_user, name='assign_run'),
]

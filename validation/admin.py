from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import Exam, Run, ModelVersion

@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('external_id', 'version', 'created_at', 'updated_at')
    list_filter = ('version', 'created_at', 'updated_at')
    search_fields = ('external_id', 'image_path')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)

@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    list_display = ('version_number', 'model_name', 'model_type', 'created_at', 'updated_at')
    list_filter = ('model_type', 'created_at', 'updated_at')
    search_fields = ('version_number', 'model_name', 'description')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)

@admin.register(Run)
class RunAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'run_date', 'get_exam_count')
    list_filter = ('status', 'run_date')
    search_fields = ('name', 'description')
    readonly_fields = ('run_date',)
    ordering = ('-run_date',)
    filter_horizontal = ('exams',)

    def get_exam_count(self, obj):
        return obj.get_exam_count()
    get_exam_count.short_description = 'Exam Count'

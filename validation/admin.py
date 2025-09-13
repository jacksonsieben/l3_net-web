from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.contrib import messages
from django.db import transaction
import random
from .models import Exam, Run, ModelVersion

@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('external_id', 'version', 'created_at', 'updated_at')
    list_filter = ('version', 'created_at', 'updated_at')
    search_fields = ('external_id', 'image_path')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    
    actions = ['shuffle_selected_external_ids', 'shuffle_selected_image_paths', 'shuffle_all_exams']

    def shuffle_selected_external_ids(self, request, queryset):
        """Shuffle external IDs among selected exams"""
        exam_list = list(queryset)
        if len(exam_list) < 2:
            self.message_user(
                request, 
                "Need at least 2 exams to shuffle", 
                level=messages.WARNING
            )
            return
        
        try:
            with transaction.atomic():
                # Get external IDs
                external_ids = [exam.external_id for exam in exam_list]
                shuffled_ids = external_ids.copy()
                random.shuffle(shuffled_ids)
                
                # Update each exam with shuffled external ID
                for exam, new_external_id in zip(exam_list, shuffled_ids):
                    exam.external_id = new_external_id
                    exam.save(update_fields=['external_id'])
                
                self.message_user(
                    request, 
                    f"Successfully shuffled external IDs for {len(exam_list)} exams", 
                    level=messages.SUCCESS
                )
        except Exception as e:
            self.message_user(
                request, 
                f"Error shuffling external IDs: {e}", 
                level=messages.ERROR
            )
    
    shuffle_selected_external_ids.short_description = "Shuffle external IDs of selected exams"

    def shuffle_selected_image_paths(self, request, queryset):
        """Shuffle image paths among selected exams"""
        exam_list = list(queryset)
        if len(exam_list) < 2:
            self.message_user(
                request, 
                "Need at least 2 exams to shuffle", 
                level=messages.WARNING
            )
            return
        
        try:
            with transaction.atomic():
                # Get image paths
                image_paths = [exam.image_path for exam in exam_list]
                shuffled_paths = image_paths.copy()
                random.shuffle(shuffled_paths)
                
                # Update each exam with shuffled image path
                for exam, new_image_path in zip(exam_list, shuffled_paths):
                    exam.image_path = new_image_path
                    exam.save(update_fields=['image_path'])
                
                self.message_user(
                    request, 
                    f"Successfully shuffled image paths for {len(exam_list)} exams", 
                    level=messages.SUCCESS
                )
        except Exception as e:
            self.message_user(
                request, 
                f"Error shuffling image paths: {e}", 
                level=messages.ERROR
            )
    
    shuffle_selected_image_paths.short_description = "Shuffle image paths of selected exams"

    def shuffle_all_exams(self, request, queryset):
        """Shuffle all exams in the database (not just selected ones)"""
        try:
            count = Exam.shuffle_all()
            self.message_user(
                request, 
                f"Successfully shuffled all {count} exams in the database", 
                level=messages.SUCCESS
            )
        except Exception as e:
            self.message_user(
                request, 
                f"Error shuffling all exams: {e}", 
                level=messages.ERROR
            )
    
    shuffle_all_exams.short_description = "Shuffle ALL exams in database (ignores selection)"

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

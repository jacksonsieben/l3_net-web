from rest_framework import serializers
from .models import (
    Exam, Run, ModelVersion, Polygon, 
    PredVertebra, PredSeverity, Validation, RunAssignment
)
from .enums.vertebra_name import VertebraName
from .enums.severity import Severity


class PolygonSerializer(serializers.ModelSerializer):
    """Serializer for polygon/bounding box data."""
    
    class Meta:
        model = Polygon
        fields = ['x1', 'y1', 'x2', 'y2']


class ModelVersionSerializer(serializers.ModelSerializer):
    """Serializer for model version data."""
    
    class Meta:
        model = ModelVersion
        fields = ['id', 'version_number', 'model_name', 'model_type', 'description']


class ExamSerializer(serializers.ModelSerializer):
    """Serializer for exam data."""
    
    class Meta:
        model = Exam
        fields = ['id', 'external_id', 'image_path', 'created_at']
        read_only_fields = ['id', 'created_at']


class ExamCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new exams."""
    
    class Meta:
        model = Exam
        fields = ['external_id', 'image_path']
    
    def validate_external_id(self, value):
        """Validate that external_id is unique."""
        if Exam.objects.filter(external_id=value).exists():
            raise serializers.ValidationError("An exam with this external ID already exists.")
        return value


class PredVertebraSerializer(serializers.ModelSerializer):
    """Serializer for vertebra predictions."""
    polygon = PolygonSerializer()
    model_version = ModelVersionSerializer(read_only=True)
    model_version_id = serializers.IntegerField(write_only=True)
    exam_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = PredVertebra
        fields = [
            'id', 'name', 'confidence', 'predicted_at',
            'polygon', 'model_version', 'model_version_id', 'exam_id'
        ]
        read_only_fields = ['id', 'predicted_at']
    
    def create(self, validated_data):
        polygon_data = validated_data.pop('polygon')
        polygon = Polygon.objects.create(**polygon_data)
        validated_data['polygon'] = polygon
        return super().create(validated_data)


class PredSeveritySerializer(serializers.ModelSerializer):
    """Serializer for severity predictions."""
    bounding_box = PolygonSerializer()
    model_version = ModelVersionSerializer(read_only=True)
    model_version_id = serializers.IntegerField(write_only=True)
    exam_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = PredSeverity
        fields = [
            'id', 'severity_name', 'confidence', 'predicted_at', 'vertebrae_level',
            'bounding_box', 'model_version', 'model_version_id', 'exam_id'
        ]
        read_only_fields = ['id', 'predicted_at']
    
    def create(self, validated_data):
        bounding_box_data = validated_data.pop('bounding_box')
        bounding_box = Polygon.objects.create(**bounding_box_data)
        validated_data['bounding_box'] = bounding_box
        return super().create(validated_data)


class RunSerializer(serializers.ModelSerializer):
    """Serializer for run data."""
    exams = ExamSerializer(many=True, read_only=True)
    exam_ids = serializers.ListField(
        child=serializers.IntegerField(), 
        write_only=True, 
        required=False
    )
    
    class Meta:
        model = Run
        fields = [
            'id', 'name', 'description', 'run_date', 
            'exams', 'exam_ids'
        ]
        read_only_fields = ['id', 'run_date']
    
    def create(self, validated_data):
        exam_ids = validated_data.pop('exam_ids', [])
        run = Run.objects.create(**validated_data)
        
        if exam_ids:
            exams = Exam.objects.filter(id__in=exam_ids)
            run.exams.set(exams)
        
        return run
    
    def update(self, instance, validated_data):
        exam_ids = validated_data.pop('exam_ids', None)
        
        # Update basic fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update exam relationships if provided
        if exam_ids is not None:
            exams = Exam.objects.filter(id__in=exam_ids)
            instance.exams.set(exams)
        
        return instance


class RunWithPredictionsSerializer(serializers.ModelSerializer):
    """Serializer for creating a complete run with predictions."""
    exams = ExamSerializer(many=True, read_only=True)
    exam_ids = serializers.ListField(child=serializers.IntegerField(), write_only=True)
    vertebra_predictions = PredVertebraSerializer(many=True, write_only=True)
    severity_predictions = PredSeveritySerializer(many=True, write_only=True)
    
    class Meta:
        model = Run
        fields = [
            'id', 'name', 'description', 'run_date',
            'exams', 'exam_ids', 'vertebra_predictions', 'severity_predictions'
        ]
        read_only_fields = ['id', 'run_date']
    
    def create(self, validated_data):
        exam_ids = validated_data.pop('exam_ids')
        vertebra_predictions_data = validated_data.pop('vertebra_predictions', [])
        severity_predictions_data = validated_data.pop('severity_predictions', [])
        
        # Create the run
        run = Run.objects.create(**validated_data)
        
        # Add exams to the run
        exams = Exam.objects.filter(id__in=exam_ids)
        run.exams.set(exams)
        
        # Create vertebra predictions
        for pred_data in vertebra_predictions_data:
            polygon_data = pred_data.pop('polygon')
            polygon = Polygon.objects.create(**polygon_data)
            
            # Get the exam_id and convert to Exam instance
            exam_id = pred_data.pop('exam_id')
            exam = Exam.objects.get(id=exam_id)
            
            PredVertebra.objects.create(
                run_id=run,
                exam_id=exam,
                polygon=polygon,
                **pred_data
            )
        
        # Create severity predictions
        for pred_data in severity_predictions_data:
            bounding_box_data = pred_data.pop('bounding_box')
            bounding_box = Polygon.objects.create(**bounding_box_data)
            
            # Get the exam_id and convert to Exam instance
            exam_id = pred_data.pop('exam_id')
            exam = Exam.objects.get(id=exam_id)
            
            PredSeverity.objects.create(
                run_id=run,
                exam_id=exam,
                bounding_box=bounding_box,
                **pred_data
            )
        
        return run


class ValidationSerializer(serializers.ModelSerializer):
    """Serializer for validation data."""
    bounding_box = PolygonSerializer(required=False, allow_null=True)
    
    class Meta:
        model = Validation
        fields = [
            'id', 'is_correct', 'comment', 'severity_name',
            'bounding_box', 'validated_at'
        ]
        read_only_fields = ['id', 'validated_at']
    
    def create(self, validated_data):
        bounding_box_data = validated_data.pop('bounding_box', None)
        bounding_box = None
        
        if bounding_box_data:
            bounding_box = Polygon.objects.create(**bounding_box_data)
            validated_data['bounding_box'] = bounding_box
        
        return super().create(validated_data)


class RunAssignmentSerializer(serializers.ModelSerializer):
    """Serializer for run assignments."""
    run = RunSerializer(read_only=True)
    run_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = RunAssignment
        fields = [
            'id', 'run', 'run_id', 'assigned_at', 'is_completed',
            'completed_at', 'notes'
        ]
        read_only_fields = ['id', 'assigned_at', 'completed_at']

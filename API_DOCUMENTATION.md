# Spinal Stenosis Validation API Documentation

This API provides endpoints for creating exams and managing run information for the spinal stenosis validation system. The API is designed for backend integration and automation of the validation workflow.

## Authentication

**⚠️ Admin Access Required**: All API endpoints (except status and token) require admin privileges.

### Token Authentication

The API uses token-based authentication. You must first obtain a token using your admin credentials, then include it in the Authorization header for all subsequent requests.

#### 1. Obtain Authentication Token

```http
POST /api/auth/token/
Content-Type: application/json

{
    "email": "admin@email.com",
    "password": "your_password"
}
```

**Response:**
```json
{
    "token": "e408ce8a4f67e5d3446bef0cb02fb189bf23d68e",
    "user_id": 2,
    "email": "admin@email.com",
    "full_name": "Admin User"
}
```

#### 2. Using the Token

Include the token in the Authorization header for all API requests:

```http
Authorization: Token e408ce8a4f67e5d3446bef0cb02fb189bf23d68e
```

## Base URL

All API endpoints are available under `/api/`

## Endpoints

### Authentication Endpoints

#### 1. API Status (Public)
Check if the API is working and see available endpoints.

```http
GET /api/status/
```

**Response:**
```json
{
    "status": "OK",
    "message": "Spinal Stenosis Validation API is running",
    "user": "admin@email.com",
    "endpoints": {
        "exams": "/api/exams/",
        "runs": "/api/runs/",
        "model_versions": "/api/model-versions/",
        "create_run_with_predictions": "/api/runs/with-predictions/",
        "assign_run": "/api/assign-run/",
        "status": "/api/status/"
    }
}
```

#### 2. User Profile
Get current user's profile information.

```http
GET /api/auth/profile/
Authorization: Token your_token_here
```

**Response:**
```json
{
    "user_id": 2,
    "email": "admin@email.com",
    "full_name": "Admin User",
    "is_staff": true,
    "is_active": true,
    "date_joined": "2025-06-11T08:07:47.319208Z"
}
```

#### 3. Logout
Logout user by deleting their token.

```http
POST /api/auth/logout/
Authorization: Token your_token_here
```

**Response:**
```json
{
    "message": "Successfully logged out"
}
```

### Exam Management

#### 4. Create New Exam

Create a new exam in the system.

```http
POST /api/exams/
Authorization: Token your_token_here
Content-Type: application/json

{
    "external_id": "EXAM-2025-001",
    "image_path": "https://example.com/scan.png"
}
```

**Response:**
```json
{
    "id": 1,
    "external_id": "EXAM-2025-001",
    "image_path": "https://example.com/scan.png",
    "created_at": "2025-06-11T10:30:00Z"
}
```

#### 5. List All Exams

Get a paginated list of all exams in the system.

```http
GET /api/exams/
Authorization: Token your_token_here
```

**Response:**
```json
{
    "count": 10,
    "next": null,
    "previous": null,
    "results": [
        {
            "id": 1,
            "external_id": "EXAM-2025-001",
            "image_path": "https://example.com/scan.png",
            "created_at": "2025-06-11T10:30:00Z"
        }
    ]
}
```

#### 6. Get Exam Details

Retrieve details of a specific exam by ID.

```http
GET /api/exams/{id}/
Authorization: Token your_token_here
```

#### 7. Get Exam by External ID

Retrieve details of a specific exam by its external_id.

```http
GET /api/exams/external/{external_id}/
Authorization: Token your_token_here
```

**Example:**
```bash
curl -X GET http://localhost:8000/api/exams/external/EXAM-2025-001/ \
  -H "Authorization: Token your_token_here"
```

**Response:**
```json
{
    "id": 1,
    "external_id": "EXAM-2025-001",
    "image_path": "https://example.com/scan.png",
    "created_at": "2025-06-11T10:30:00Z"
}
```

#### 8. Update Exam

Update an existing exam.

```http
PUT /api/exams/{id}/
Authorization: Token your_token_here
Content-Type: application/json

{
    "external_id": "EXAM-2025-001-UPDATED",
    "image_path": "https://example.com/updated-scan.png"
}
```

#### 9. Delete Exam

Delete an exam from the system.

```http
DELETE /api/exams/{id}/
Authorization: Token your_token_here
```

### Model Version Management

#### 10. Create Model Version

Create a new model version for predictions.

```http
POST /api/model-versions/
Authorization: Token your_token_here
Content-Type: application/json

{
    "version_number": "v2.1",
    "model_name": "SpineStenosis-Advanced", 
    "model_type": "classification",
    "description": "Advanced model with improved accuracy",
    "model_path": "/path/to/model/file.pkl"
}
```

**Fields:**
- `version_number` (required): Version number of the model
- `model_name` (required): Name of the model
- `model_type` (required): Type of the model (e.g., "classification", "regression")
- `description` (optional): Description of the model version
- `model_path` (optional): Path to the model file

**Response:**
```json
{
    "id": 1,
    "version_number": "v2.1",
    "model_name": "SpineStenosis-Advanced",
    "model_type": "classification", 
    "description": "Advanced model with improved accuracy",
    "model_path": "/path/to/model/file.pkl"
}
```

#### 11. List Model Versions

Get all model versions.

```http
GET /api/model-versions/
Authorization: Token your_token_here
```

#### 12. Find Model Version by Version and Type

Find a specific model version by its version number and model type.

```http
GET /api/model-versions/find/?version_number=1.0&model_type=classification
Authorization: Token your_token_here
```

**Parameters:**
- `version_number` (required): The version number of the model (e.g., "1.0", "2.1.3")
- `model_type` (required): The type of the model (e.g., "classification", "regression")

**Response:**
```json
{
    "success": true,
    "data": {
        "id": 1,
        "version_number": "1.0",
        "model_name": "Spinal Stenosis Classifier",
        "model_type": "classification",
        "description": "Initial version of the classifier model",
        "model_path": "/path/to/model/file.pkl"
    }
}
```

**Error Response (404):**
```json
{
    "success": false,
    "message": "Model version not found with version_number=\"1.0\" and model_type=\"classification\""
}
```

### Run Management

#### 13. Create Simple Run

Create a basic run and assign exams to it.

```http
POST /api/runs/
Authorization: Token your_token_here
Content-Type: application/json

{
    "name": "Quality Control Batch 3",
    "description": "Third batch of quality control validation",
    "exam_ids": [1, 2, 3]
}
```

**Response:**
```json
{
    "id": 5,
    "name": "Quality Control Batch 3",
    "description": "Third batch of quality control validation",
    "run_date": "2025-06-11T10:30:00Z",
    "exams": [1, 2, 3]
}
```

#### 14. List All Runs

Get all runs in the system.

```http
GET /api/runs/
Authorization: Token your_token_here
```

#### 15. Get Run Details

Get details of a specific run.

```http
GET /api/runs/{id}/
Authorization: Token your_token_here
```

#### 16. Create Run with Predictions (Complete)

Create a complete run with exams and all predictions in one API call.

```http
POST /api/runs/with-predictions/
Authorization: Token your_token_here
Content-Type: application/json

{
    "name": "AI Model Run - June 2025",
    "description": "Automated predictions from latest AI model",
    "exam_ids": [1, 2],
    "vertebra_predictions": [
        {
            "name": "L1",
            "confidence": 0.95,
            "exam_id": 1,
            "model_version_id": 1,
            "polygon": {
                "x1": 0.1,
                "y1": 0.2,
                "x2": 0.3,
                "y2": 0.4
            }
        },
        {
            "name": "L2",
            "confidence": 0.92,
            "exam_id": 2,
            "model_version_id": 1,
            "polygon": {
                "x1": 0.15,
                "y1": 0.25,
                "x2": 0.35,
                "y2": 0.45
            }
        }
    ],
    "severity_predictions": [
        {
            "severity_name": "MODERATE",
            "confidence": 0.87,
            "vertebrae_level": "L3/L4",
            "exam_id": 1,
            "model_version_id": 1,
            "bounding_box": {
                "x1": 0.12,
                "y1": 0.22,
                "x2": 0.32,
                "y2": 0.42
            }
        },
        {
            "severity_name": "SEVERE",
            "confidence": 0.89,
            "vertebrae_level": "L4/L5",
            "exam_id": 2,
            "model_version_id": 1,
            "bounding_box": {
                "x1": 0.17,
                "y1": 0.27,
                "x2": 0.37,
                "y2": 0.47
            }
        }
    ]
}
```

**Response:**
```json
{
    "success": true,
    "message": "Run \"AI Model Run - June 2025\" created successfully with predictions.",
    "run_id": 5,
    "run": {
        "id": 5,
        "name": "AI Model Run - June 2025",
        "description": "Automated predictions from latest AI model",
        "run_date": "2025-06-11T10:30:00Z",
        "exams": [1, 2]
    }
}
```

#### 17. Add Predictions to Existing Run

Add more predictions to an existing run.

```http
POST /api/runs/5/predictions/
Authorization: Token your_token_here
Content-Type: application/json

{
    "vertebra_predictions": [
        {
            "name": "L3",
            "confidence": 0.88,
            "exam_id": 1,
            "model_version_id": 1,
            "polygon": {
                "x1": 0.2,
                "y1": 0.3,
                "x2": 0.4,
                "y2": 0.5
            }
        }
    ],
    "severity_predictions": [
        {
            "severity_name": "MILD",
            "confidence": 0.91,
            "vertebrae_level": "L2/L3",
            "exam_id": 1,
            "model_version_id": 1,
            "bounding_box": {
                "x1": 0.22,
                "y1": 0.32,
                "x2": 0.42,
                "y2": 0.52
            }
        }
    ]
}
```

**Response:**
```json
{
    "success": true,
    "message": "Added 1 vertebra predictions and 1 severity predictions to run \"AI Model Run - June 2025\".",
    "created": {
        "vertebrae_count": 1,
        "severities_count": 1
    }
}
```

#### 18. Get Run Predictions

Retrieve all predictions for a specific run.

```http
GET /api/runs/5/predictions/get/
Authorization: Token your_token_here
```

**Response:**
```json
{
    "run_id": 5,
    "run_name": "AI Model Run - June 2025",
    "vertebra_predictions": [
        {
            "id": 1,
            "name": "L1",
            "confidence": 0.95,
            "model_version_id": 1,
            "polygon": {
                "id": 1,
                "x1": 0.1,
                "y1": 0.2,
                "x2": 0.3,
                "y2": 0.4
            }
        }
    ],
    "severity_predictions": [
        {
            "id": 1,
            "severity_name": "MODERATE",
            "confidence": 0.87,
            "vertebrae_level": "L3/L4",
            "model_version_id": 1,
            "bounding_box": {
                "id": 1,
                "x1": 0.12,
                "y1": 0.22,
                "x2": 0.32,
                "y2": 0.42
            }
        }
    ]
}
```

### User Assignment Management

#### 19. Assign Run to User

Assign a run to a user for validation.

```http
POST /api/assign-run/
Authorization: Token your_token_here
Content-Type: application/json

{
    "run_id": 5,
    "user_id": 2,
    "notes": "Please prioritize this validation"
}
```

**Response:**
```json
{
    "success": true,
    "message": "Run \"AI Model Run - June 2025\" assigned to user@example.com successfully.",
    "assignment": {
        "id": 1,
        "run_id": 5,
        "user_id": 2,
        "assigned_by": "admin@email.com",
        "assigned_at": "2025-06-11T10:30:00Z",
        "notes": "Please prioritize this validation",
        "completed": false
    }
}
```

## Data Models and Validation

### Required Fields

#### Exam
- `external_id`: Unique identifier for the exam (string, required)
- `image_path`: URL or path to the medical image (string, required)

#### Run
- `name`: Human-readable name for the run (string, required)
- `description`: Description of the run purpose (string, optional)
- `exam_ids`: List of exam IDs to include in the run (array, required)

#### Model Version
- `version_number`: Version identifier (string, required)
- `model_name`: Name of the model (string, required)
- `model_type`: Type of model (string, required)
- `description`: Model description (string, optional)

#### Vertebra Prediction
- `name`: Vertebra identifier (enum, required)
- `confidence`: Confidence score 0.0-1.0 (float, required)
- `exam_id`: ID of the exam this prediction belongs to (integer, required)
- `model_version_id`: ID of the model version (integer, required)
- `polygon`: Bounding polygon coordinates (object, required)

#### Severity Prediction
- `severity_name`: Severity level (enum, required)
- `confidence`: Confidence score 0.0-1.0 (float, required)
- `vertebrae_level`: Vertebra level where severity is detected (enum, required)
- `exam_id`: ID of the exam this prediction belongs to (integer, required)
- `model_version_id`: ID of the model version (integer, required)
- `bounding_box`: Bounding box coordinates (object, required)

### Enumerated Values

#### Vertebra Names
Available values: `L1`, `L2`, `L3`, `L4`, `L5`, `S1`, `T12`, `UNKNOWN`

#### Severity Levels
Available values: `NORMAL`, `MILD`, `MODERATE`, `SEVERE`, `UNKNOWN`

#### Vertebra Levels
Available values: `L1/L2`, `L2/L3`, `L3/L4`, `L4/L5`, `L5/S1`, `UNKNOWN`

#### Vertebra Levels
Available values: `L1/L2`, `L2/L3`, `L3/L4`, `L4/L5`, `L5/S1`, `Unknown`

### Coordinate System

#### Polygon/Bounding Box Coordinates
All coordinates should be normalized values between 0.0 and 1.0:
- `x1`, `y1`: Top-left corner
- `x2`, `y2`: Bottom-right corner

Example:
```json
{
    "x1": 0.1,    // 10% from left edge
    "y1": 0.2,    // 20% from top edge
    "x2": 0.3,    // 30% from left edge
    "y2": 0.4     // 40% from top edge
}
```

## Error Handling

The API returns standard HTTP status codes:
- `200`: Success
- `201`: Created
- `400`: Bad Request (validation errors)
- `401`: Unauthorized (invalid or missing token)
- `403`: Forbidden (admin access required)
- `404`: Not Found
- `500`: Internal Server Error

### Error Response Format

**Authentication Errors:**
```json
{
    "detail": "Invalid token."
}
```

**Validation Errors:**
```json
{
    "success": false,
    "errors": {
        "external_id": ["This field is required."],
        "image_path": ["Enter a valid URL."]
    }
}
```

**Permission Errors:**
```json
{
    "detail": "You do not have permission to perform this action."
}
```

## Complete Example Workflow

Here's a complete example of using the API to create exams, runs, and predictions:

### Step 1: Authenticate

```bash
# Get authentication token
curl -X POST http://localhost:8000/api/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@email.com","password":"1234"}'
```

Response:
```json
{
    "token": "e408ce8a4f67e5d3446bef0cb02fb189bf23d68e",
    "user_id": 2,
    "email": "admin@email.com",
    "full_name": "Admin User"
}
```

### Step 2: Create Exams

```bash
# Create first exam
curl -X POST http://localhost:8000/api/exams/ \
  -H "Authorization: Token e408ce8a4f67e5d3446bef0cb02fb189bf23d68e" \
  -H "Content-Type: application/json" \
  -d '{
    "external_id": "EXAM-API-001",
    "image_path": "https://example.com/scan1.jpg"
  }'

# Create second exam  
curl -X POST http://localhost:8000/api/exams/ \
  -H "Authorization: Token e408ce8a4f67e5d3446bef0cb02fb189bf23d68e" \
  -H "Content-Type: application/json" \
  -d '{
    "external_id": "EXAM-API-002", 
    "image_path": "https://example.com/scan2.jpg"
  }'
```

### Step 3: Create Model Version

```bash
curl -X POST http://localhost:8000/api/model-versions/ \
  -H "Authorization: Token e408ce8a4f67e5d3446bef0cb02fb189bf23d68e" \
  -H "Content-Type: application/json" \
  -d '{
    "version_number": "v1.0",
    "model_name": "StenoPred",
    "model_type": "classification",
    "description": "Initial production model"
  }'
```

### Step 4: Create Run with Predictions

```bash
curl -X POST http://localhost:8000/api/runs/with-predictions/ \
  -H "Authorization: Token e408ce8a4f67e5d3446bef0cb02fb189bf23d68e" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Production Run June 2025",
    "description": "Automated analysis of new patient scans",
    "exam_ids": [1, 2],
    "vertebra_predictions": [
      {
        "name": "L3",
        "confidence": 0.94,
        "exam_id": 1,
        "model_version_id": 1,
        "polygon": {
          "x1": 0.2,
          "y1": 0.3,
          "x2": 0.4,
          "y2": 0.5
        }
      }
    ],
    "severity_predictions": [
      {
        "severity_name": "MODERATE",
        "confidence": 0.88,
        "vertebrae_level": "L3/L4",
        "exam_id": 1,
        "model_version_id": 1,
        "bounding_box": {
          "x1": 0.22,
          "y1": 0.32,
          "x2": 0.42,
          "y2": 0.52
        }
      }
    ]
  }'
```

### Step 5: Assign Run for Validation

```bash
curl -X POST http://localhost:8000/api/assign-run/ \
  -H "Authorization: Token e408ce8a4f67e5d3446bef0cb02fb189bf23d68e" \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": 1,
    "user_id": 3,
    "notes": "High priority validation needed"
  }'
```

## Rate Limiting and Best Practices

- **Authentication**: Store tokens securely and refresh when they expire
- **Bulk Operations**: Use the `runs/with-predictions/` endpoint for creating runs with many predictions
- **Error Handling**: Always check response status codes and handle errors appropriately
- **Data Validation**: Ensure coordinates are normalized (0.0-1.0) before sending
- **Testing**: Use the `/api/status/` endpoint to verify API availability

## Support

For technical support or questions about the API, please contact the development team with:
- API endpoint you're trying to use
- Request payload (sanitized)
- Response received
- Expected behavior

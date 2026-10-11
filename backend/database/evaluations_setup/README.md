# Evaluations API Implementation

## Overview

This directory contains the setup script for populating the evaluations table with benchmark evaluation data from the legacy PapersWithCode data dump.

## What Was Implemented

### 1. API Models (`backend/models/evaluations.py`)
- **Evaluation**: Response model for individual evaluations
- **Evaluations**: Paginated response model
- **EvaluationCreateRequest**: Request model for creating evaluations
- **EvaluationUpdateRequest**: Request model for updating evaluations

### 2. Service Layer (`backend/services/evaluation_service.py`)
- **EvaluationService**: Service class handling evaluation business logic
  - `get_evaluations()`: List evaluations with filtering and pagination
  - `get_evaluation()`: Get single evaluation by ID
  - `search_evaluations()`: Search by model name or methodology
  - `create_evaluation()`: Create new evaluation

### 3. API Router (`backend/routers/evaluations.py`)
- **GET /api/v1/evaluations/**: List all evaluations
  - Query params: `page`, `page_size`, `paper_id`, `task_id`, `dataset_id`, `q`, `ordering`
- **GET /api/v1/evaluations/{evaluation_id}**: Get specific evaluation

### 4. Database Population (`import_detr_evaluation.py`)
- Imports DETR evaluation from legacy PapersWithCode data
- Links paper (ArXiv: 2005.12872) with task (Object Detection) and dataset (COCO)
- Stores performance metrics (AP, AP50, AP75, etc.)

## Current Database State

- **Papers**: 53,450
- **Tasks**: 30
- **Datasets**: 1 (COCO)
- **Evaluations**: 1 (DETR on COCO)

## DETR Evaluation Details

- **Paper**: End-to-End Object Detection with Transformers
- **ArXiv ID**: 2005.12872
- **Task**: Object Detection (ID: 2)
- **Dataset**: COCO (Common Objects in Context, ID: 1)
- **Model**: DETR-DC5 (ResNet-101)
- **Metrics**:
  - box AP: 44.9
  - AP50: 64.7
  - AP75: 47.7
  - APS: 23.7
  - APM: 49.5
  - APL: 62.3
- **Evaluated On**: 2020-05-26

## Usage

### Import DETR Evaluation

```bash
uv run --env-file backend/keys.env python backend/database/evaluations_setup/import_detr_evaluation.py
```

### API Examples

```bash
# List all evaluations
curl http://localhost:8000/api/v1/evaluations/

# Get specific evaluation
curl http://localhost:8000/api/v1/evaluations/1

# Filter by paper ID
curl http://localhost:8000/api/v1/evaluations/?paper_id=3625

# Filter by task and dataset
curl http://localhost:8000/api/v1/evaluations/?task_id=2&dataset_id=1

# Search for DETR
curl http://localhost:8000/api/v1/evaluations/?q=DETR
```

## Next Steps

This implementation provides a foundation for:
1. Importing more evaluations from the legacy data
2. Adding new evaluations via API endpoints
3. Building leaderboards and performance comparisons
4. Filtering and searching evaluation results

## Files Created

- `backend/models/evaluations.py` (Evaluation models added)
- `backend/services/evaluation_service.py`
- `backend/routers/evaluations.py`
- `backend/database/evaluations_setup/import_detr_evaluation.py`
- `backend/main.py` (Router registration added)

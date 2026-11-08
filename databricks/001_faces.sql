-- Face data (run first). Templates only, never photos; matching runs locally in face_api. Vector Search index is optional (see face_api/app/databricks_store.py).
CREATE SCHEMA IF NOT EXISTS workspace.cashcan_faces;
CREATE TABLE IF NOT EXISTS workspace.cashcan_faces.users (user_id STRING NOT NULL, wallet STRING, consented_at TIMESTAMP, created_at TIMESTAMP, status STRING);
CREATE TABLE IF NOT EXISTS workspace.cashcan_faces.face_templates (template_id STRING NOT NULL, user_id STRING NOT NULL, embedding ARRAY<FLOAT>, model_version STRING, created_at TIMESTAMP) TBLPROPERTIES (delta.enableChangeDataFeed = true);

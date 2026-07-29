# Use official lightweight Python image
FROM python:3.11-slim

# Install system dependencies needed for parsing PDFs (e.g. libgl1/glib for OpenCV and camelot)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend files
COPY backend/ .

# Expose port (default to 8080 if not specified, but dynamically overridden by hosts)
EXPOSE 8080

# Run FastAPI app using shell form to expand the PORT environment variable
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}

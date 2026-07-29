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

# Expose port (Hugging Face Spaces strictly requires listening on port 7860)
ENV PORT=7860
EXPOSE 7860

# Run FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]

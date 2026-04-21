FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Create data directory for SQLite
RUN mkdir -p /app/data

# Expose port
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Command to run the FastApi application
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
